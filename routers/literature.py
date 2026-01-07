from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import os
import base64
import pandas as pd
import asyncio
from concurrent.futures import ThreadPoolExecutor
import logging
import json
import time

from services.project_paths import ensure_project_folders
from literature.pubmed_runner import run_pubmed_pipeline

router = APIRouter(prefix="/api/literature", tags=["Literature Screening"])

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Thread pool for async execution
executor = ThreadPoolExecutor(max_workers=3, thread_name_prefix="literature_worker")

# Store active searches
active_searches = {}


def update_progress(project_id: str, progress: int, status: str, message: str = ""):
    """Update progress for a project"""
    literature_folder = f"database/{project_id}/literature"
    os.makedirs(literature_folder, exist_ok=True)
    
    status_file = os.path.join(literature_folder, "search_status.json")
    status_data = {
        "status": status,
        "progress": progress,
        "message": message,
        "timestamp": time.time()
    }
    
    with open(status_file, "w") as f:
        json.dump(status_data, f)
    
    active_searches[project_id] = status_data


def check_cancellation(project_id: str) -> bool:
    """Check if search was cancelled"""
    literature_folder = f"database/{project_id}/literature"
    cancel_file = os.path.join(literature_folder, "cancel_search.flag")
    return os.path.exists(cancel_file)


def run_pipeline_with_progress(keywords_path, literature_folder, params, project_id):
    """Wrapper to run pipeline with progress updates"""
    try:
        # Initial progress
        update_progress(project_id, 10, "running", "Initializing search...")
        
        if check_cancellation(project_id):
            update_progress(project_id, 0, "cancelled", "Search cancelled by user")
            return None
        
        update_progress(project_id, 30, "running", "Querying PubMed database...")
        
        # Run the actual pipeline
        excel_path = run_pubmed_pipeline(
            keywords_path, 
            literature_folder, 
            params, 
            project_id
        )
        
        if check_cancellation(project_id):
            update_progress(project_id, 0, "cancelled", "Search cancelled by user")
            return None
        
        update_progress(project_id, 90, "running", "Finalizing results...")
        
        return excel_path
        
    except Exception as e:
        update_progress(project_id, 0, "error", str(e))
        raise


@router.post("/run")
async def run_pipeline(
    project_id: str = Form(...),
    keywordsFile: UploadFile = File(...),
    applyDateFilter: str = Form("false"),
    fromDate: str = Form(""),
    toDate: str = Form(""),
    abstract: str = Form("false"),
    freeFullText: str = Form("false"),
    fullText: str = Form("false"),
):
    try:
        paths = ensure_project_folders(project_id)
        literature_folder = paths["literature"]

        # Clear any previous cancel flags
        cancel_file = os.path.join(literature_folder, "cancel_search.flag")
        if os.path.exists(cancel_file):
            os.remove(cancel_file)

        # Save uploaded keywords file
        keywords_path = os.path.join(literature_folder, "keywords.xlsx")
        with open(keywords_path, "wb") as f:
            f.write(await keywordsFile.read())

        # Convert string to boolean
        def to_bool(v):
            return v.lower() == "true"

        params = {
            "applyDateFilter": to_bool(applyDateFilter),
            "fromDate": fromDate,
            "toDate": toDate,
            "abstract": to_bool(abstract),
            "freeFullText": to_bool(freeFullText),
            "fullText": to_bool(fullText),
        }

        logger.info(f"Starting literature search for project {project_id}")
        update_progress(project_id, 5, "running", "Starting search...")

        # Run pipeline with progress tracking
        try:
            loop = asyncio.get_event_loop()
            
            # Create task with timeout (30 minutes max)
            excel_path = await asyncio.wait_for(
                loop.run_in_executor(
                    executor,
                    run_pipeline_with_progress,
                    keywords_path,
                    literature_folder,
                    params,
                    project_id
                ),
                timeout=1800.0  # 30 minutes
            )

            # Check if cancelled
            if excel_path is None and check_cancellation(project_id):
                update_progress(project_id, 0, "cancelled", "Search cancelled")
                raise HTTPException(status_code=499, detail="Search cancelled by user")

            # Check if file was created
            if not excel_path or not os.path.exists(excel_path):
                raise Exception("Pipeline completed but output file not found")

            # Return as base64
            with open(excel_path, "rb") as f:
                excel_bytes = f.read()

            logger.info(f"Literature search completed successfully for project {project_id}")
            update_progress(project_id, 100, "completed", "Search completed successfully")

            return {
                "status": "success",
                "excelFile": base64.b64encode(excel_bytes).decode(),
                "message": "Literature search completed successfully"
            }

        except asyncio.TimeoutError:
            logger.error(f"Pipeline timeout for project {project_id}")
            update_progress(project_id, 0, "error", "Search timed out after 30 minutes")
            
            # Check if partial results exist
            partial_path = os.path.join(literature_folder, "All-Merged.xlsx")
            if os.path.exists(partial_path):
                with open(partial_path, "rb") as f:
                    excel_bytes = f.read()
                
                return JSONResponse(
                    status_code=206,
                    content={
                        "status": "partial",
                        "excelFile": base64.b64encode(excel_bytes).decode(),
                        "message": "Search timed out. Partial results available.",
                        "error": "Timeout after 30 minutes"
                    }
                )
            else:
                raise HTTPException(
                    status_code=504,
                    detail="Literature search timed out after 30 minutes"
                )
        
        except Exception as pipeline_error:
            logger.error(f"Pipeline error for project {project_id}: {str(pipeline_error)}")
            
            # Check if partial results exist
            partial_path = os.path.join(literature_folder, "All-Merged.xlsx")
            if os.path.exists(partial_path):
                with open(partial_path, "rb") as f:
                    excel_bytes = f.read()
                
                update_progress(project_id, 100, "partial", "Completed with errors")
                
                return JSONResponse(
                    status_code=206,
                    content={
                        "status": "partial",
                        "excelFile": base64.b64encode(excel_bytes).decode(),
                        "message": "Search completed with some errors. Partial results available.",
                        "error": str(pipeline_error)
                    }
                )
            else:
                update_progress(project_id, 0, "error", str(pipeline_error))
                raise HTTPException(
                    status_code=500,
                    detail=f"Literature search failed: {str(pipeline_error)}"
                )

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in literature search: {str(e)}")
        update_progress(project_id, 0, "error", str(e))
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process literature search: {str(e)}"
        )


@router.get("/existing")
def get_existing(project_id: str):
    try:
        master_path = f"database/{project_id}/literature/All-Merged.xlsx"

        if not os.path.exists(master_path):
            return {"exists": False}

        df = pd.read_excel(master_path).fillna("")

        with open(master_path, "rb") as f:
            excel_bytes = f.read()

        return {
            "exists": True,
            "masterSheet": df.to_dict(orient="records"),
            "excelFile": base64.b64encode(excel_bytes).decode(),
        }
    
    except Exception as e:
        logger.error(f"Error loading existing data: {str(e)}")
        return {"exists": False, "error": str(e)}


@router.get("/status/{project_id}")
def get_search_status(project_id: str):
    """Check the status of an ongoing literature search"""
    try:
        literature_folder = f"database/{project_id}/literature"
        
        if not os.path.exists(literature_folder):
            return {"status": "not_started", "progress": 0, "message": ""}
        
        # Check status file
        status_file = os.path.join(literature_folder, "search_status.json")
        if os.path.exists(status_file):
            with open(status_file, "r") as f:
                status_data = json.load(f)
            
            # Check if status is stale (older than 5 minutes)
            if time.time() - status_data.get("timestamp", 0) > 300:
                status_data["status"] = "stale"
                status_data["message"] = "Status may be outdated"
            
            return status_data
        
        # Check if results exist
        results_file = os.path.join(literature_folder, "All-Merged.xlsx")
        if os.path.exists(results_file):
            return {"status": "completed", "progress": 100, "message": "Search completed"}
        
        return {"status": "unknown", "progress": 0, "message": ""}
    
    except Exception as e:
        logger.error(f"Error checking status: {str(e)}")
        return {"status": "error", "progress": 0, "error": str(e), "message": str(e)}


@router.post("/cancel/{project_id}")
def cancel_search(project_id: str):
    """Cancel an ongoing literature search"""
    try:
        literature_folder = f"database/{project_id}/literature"
        cancel_file = os.path.join(literature_folder, "cancel_search.flag")
        
        # Create cancel flag file
        os.makedirs(literature_folder, exist_ok=True)
        with open(cancel_file, "w") as f:
            f.write("cancelled")
        
        update_progress(project_id, 0, "cancelled", "Search cancelled by user")
        
        return {"status": "success", "message": "Search cancellation requested"}
    
    except Exception as e:
        logger.error(f"Error cancelling search: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail=f"Failed to cancel search: {str(e)}"
        )