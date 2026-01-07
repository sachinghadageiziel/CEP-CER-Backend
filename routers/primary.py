from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import os
import base64
import pandas as pd
import traceback
import logging

from primary.primary_runner import run_primary_screening

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/primary", tags=["Primary Screening"])


@router.post("/run")
async def primary_screening(
    project_id: str = Form(...),
    all_merged: UploadFile = File(...),
    ifu_pdf: UploadFile = File(...),
):
    """
    Upload All-Merged.xlsx and IFU.pdf for a project.
    Saves files in database/{project_id}/primary/
    Returns base64 encoded Excel results.
    """
    
    logger.info(f"Starting primary screening for project: {project_id}")
    logger.info(f"Excel file: {all_merged.filename}")
    logger.info(f"PDF file: {ifu_pdf.filename}")
    
    try:
        # Create project folder
        project_folder = os.path.join("database", project_id, "primary")
        os.makedirs(project_folder, exist_ok=True)
        logger.info(f"Created/verified folder: {project_folder}")

        # Save Excel file
        excel_path = os.path.join(project_folder, "All-Merged.xlsx")
        logger.info(f"Saving Excel to: {excel_path}")
        with open(excel_path, "wb") as f:
            content = await all_merged.read()
            f.write(content)
            logger.info(f"Excel file saved, size: {len(content)} bytes")

        # Save PDF file
        ifu_path = os.path.join(project_folder, "IFU.pdf")
        logger.info(f"Saving PDF to: {ifu_path}")
        with open(ifu_path, "wb") as f:
            content = await ifu_pdf.read()
            f.write(content)
            logger.info(f"PDF file saved, size: {len(content)} bytes")

        # Run primary screening
        logger.info("Starting run_primary_screening...")
        try:
            output_excel = run_primary_screening(excel_path, ifu_path, project_folder)
            logger.info(f"Primary screening completed. Output: {output_excel}")
        except Exception as e:
            logger.error(f"Error in run_primary_screening: {str(e)}")
            logger.error(traceback.format_exc())
            raise HTTPException(
                status_code=500, 
                detail=f"Primary screening failed: {str(e)}"
            )

        # Check if output file exists
        if not os.path.exists(output_excel):
            logger.error(f"Output file not found: {output_excel}")
            raise HTTPException(
                status_code=500,
                detail="Screening completed but output file not found"
            )

        # Read and encode output
        logger.info("Reading output file...")
        with open(output_excel, "rb") as f:
            encoded = base64.b64encode(f.read()).decode()
            logger.info(f"Output file encoded, size: {len(encoded)} chars")

        logger.info("Primary screening completed successfully!")
        return {
            "status": "success",
            "excelFile": encoded,
            "message": "Primary screening completed successfully"
        }
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Unexpected error in primary_screening: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(
            status_code=500,
            detail=f"An unexpected error occurred: {str(e)}"
        )


@router.get("/existing")
def get_existing_primary(project_id: str):
    """
    Check if primary screening result already exists.
    Returns parsed Excel + base64 file.
    """
    logger.info(f"Checking existing primary screening for project: {project_id}")
    
    try:
        output_path = f"database/{project_id}/primary/screening_results.xlsx"

        if not os.path.exists(output_path):
            logger.info(f"No existing screening results found at: {output_path}")
            return {"exists": False}

        logger.info(f"Reading existing screening results from: {output_path}")
        df = pd.read_excel(output_path).fillna("")
        logger.info(f"Found {len(df)} rows in screening results")

        with open(output_path, "rb") as f:
            excel_bytes = f.read()

        return {
            "exists": True,
            "masterSheet": df.to_dict(orient="records"),
            "excelFile": base64.b64encode(excel_bytes).decode(),
        }
    except Exception as e:
        logger.error(f"Error in get_existing_primary: {str(e)}")
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/article")
def get_primary_article(project_id: str, pmid: str):
    """Get details of a specific article by PMID"""
    logger.info(f"Getting article {pmid} for project {project_id}")
    
    try:
        path = f"database/{project_id}/primary/screening_results.xlsx"
        if not os.path.exists(path):
            return {"found": False}

        df = pd.read_excel(path).fillna("")
        row = df[df["PMID"].astype(str) == str(pmid)]

        if row.empty:
            return {"found": False}

        return {
            "found": True,
            "article": row.iloc[0].to_dict()
        }
    except Exception as e:
        logger.error(f"Error in get_primary_article: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/decision")
def update_decision(
    project_id: str = Form(...),
    pmid: str = Form(...),
    decision: str = Form(...),
    reason: str = Form("")
):
    """Update the decision for a specific article"""
    logger.info(f"Updating decision for PMID {pmid} in project {project_id}")
    
    try:
        path = f"database/{project_id}/primary/screening_results.xlsx"
        
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Screening results not found")
        
        df = pd.read_excel(path).fillna("")

        idx = df[df["PMID"].astype(str) == str(pmid)].index
        if len(idx) == 0:
            return {"updated": False, "message": "PMID not found"}

        df.loc[idx, "Decision"] = decision
        df.loc[idx, "OverrideReason"] = reason

        df.to_excel(path, index=False)
        logger.info(f"Decision updated successfully for PMID {pmid}")
        
        return {"updated": True, "message": "Decision updated successfully"}
    except Exception as e:
        logger.error(f"Error in update_decision: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/page")
def get_primary_page(
    project_id: str,
    page: int = 1,
    size: int = 20
):
    """Get paginated primary screening results"""
    logger.info(f"Getting page {page} (size {size}) for project {project_id}")
    
    try:
        path = f"database/{project_id}/primary/screening_results.xlsx"
        
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Screening results not found")
        
        df = pd.read_excel(path).fillna("")

        start = (page - 1) * size
        end = start + size

        return {
            "total": len(df),
            "page": page,
            "size": size,
            "rows": df.iloc[start:end].to_dict(orient="records")
        }
    except Exception as e:
        logger.error(f"Error in get_primary_page: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/export")
def export_results(project_id: str):
    """Export screening results as downloadable Excel file"""
    logger.info(f"Exporting results for project: {project_id}")
    
    try:
        from fastapi.responses import FileResponse
        
        path = f"database/{project_id}/primary/screening_results.xlsx"
        
        if not os.path.exists(path):
            raise HTTPException(status_code=404, detail="Screening results not found")
        
        logger.info(f"Exporting file from: {path}")
        
        return FileResponse(
            path=path,
            filename=f"primary_screening_results_{project_id}.xlsx",
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        )
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error in export_results: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))


# Health check endpoint
@router.get("/health")
def health_check():
    """Check if the API is running"""
    return {"status": "healthy", "message": "Primary screening API is running"}