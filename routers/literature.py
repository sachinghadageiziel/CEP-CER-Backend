from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from io import BytesIO
import pandas as pd
from datetime import datetime
import base64
from typing import Dict

from db.database import get_db
from literature.pubmed_runner import run_pubmed_pipeline
from db.models.literature_model import Literature

# -------------------------------
# In-memory store for uploaded keywords (per project)
keywords_memory = {}

# Store for tracking running searches and cancellation flags
running_searches: Dict[str, bool] = {}
cancellation_flags: Dict[str, bool] = {}
# -------------------------------

router = APIRouter(
    prefix="/api/literature",
    tags=["Literature Screening"]
)


@router.post("/upload-keywords")
async def upload_keywords(
    project_id: str = Form(...),
    keywordsFile: UploadFile = File(...)
):
    file_bytes = await keywordsFile.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    # Read Excel
    try:
        df = pd.read_excel(BytesIO(file_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {str(e)}")

    # Normalize column names
    df.columns = [c.strip() for c in df.columns]

    # Required columns
    required_cols = ["Keyword No.", "Keywords"]
    for col in required_cols:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Missing required column: {col}")

    keywords_memory[project_id] = []

    for _, row in df.iterrows():
        kw_raw = str(row.get("Keywords", "")).strip()
        if not kw_raw or kw_raw.lower() == "nan":
            continue  # skip empty keywords

        # Parse date range
        from_date, to_date = None, None
        date_range_raw = str(row.get("Date Range", "")).strip()
        if "to" in date_range_raw:
            parts = date_range_raw.split("to")
            if len(parts) == 2:
                try:
                    from_date = datetime.strptime(parts[0].strip(), "%d %B %Y").strftime("%Y/%m/%d")
                    to_date = datetime.strptime(parts[1].strip(), "%d %B %Y").strftime("%Y/%m/%d")
                except ValueError:
                    pass  # leave None if parsing fails

        keywords_memory[project_id].append({
            "keyword_no": str(row.get("Keyword No.", "")).strip(),
            "keyword": kw_raw,
            "filters": str(row.get("Filters", "")).strip(),
            "from_date": from_date,
            "to_date": to_date,
        })

    return {
        "status": "success",
        "project_id": project_id,
        "keywords_uploaded": len(keywords_memory[project_id])
    }


@router.post("/run")
async def run_literature_search(
    project_id: str = Form(...),
    keywordsFile: UploadFile = File(...),
    applyDateFilter: str = Form("false"),
    fromDate: str = Form(""),
    toDate: str = Form(""),
    abstract: str = Form("false"),
    freeFullText: str = Form("false"),
    fullText: str = Form("false"),
    db: Session = Depends(get_db)
):
    """
    Enhanced endpoint that handles the complete literature search with error handling
    """
    # Check if search is already running for this project
    if running_searches.get(project_id, False):
        raise HTTPException(status_code=409, detail="Search already running for this project")

    # Parse and validate the uploaded file
    file_bytes = await keywordsFile.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    try:
        df = pd.read_excel(BytesIO(file_bytes))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid Excel file: {str(e)}")

    # Normalize column names
    df.columns = [c.strip() for c in df.columns]

    # Required columns
    required_cols = ["Keyword No.", "Keywords"]
    for col in required_cols:
        if col not in df.columns:
            raise HTTPException(status_code=400, detail=f"Missing required column: {col}")

    keywords_memory[project_id] = []

    # Parse keywords and apply filters
    for _, row in df.iterrows():
        kw_raw = str(row.get("Keywords", "")).strip()
        if not kw_raw or kw_raw.lower() == "nan":
            continue

        # Use form dates if date filter is applied
        from_date_val, to_date_val = None, None
        if applyDateFilter.lower() == "true":
            from_date_val = fromDate if fromDate else None
            to_date_val = toDate if toDate else None
        else:
            # Try to parse from Excel date range column
            date_range_raw = str(row.get("Date Range", "")).strip()
            if "to" in date_range_raw:
                parts = date_range_raw.split("to")
                if len(parts) == 2:
                    try:
                        from_date_val = datetime.strptime(parts[0].strip(), "%d %B %Y").strftime("%Y/%m/%d")
                        to_date_val = datetime.strptime(parts[1].strip(), "%d %B %Y").strftime("%Y/%m/%d")
                    except ValueError:
                        pass

        keywords_memory[project_id].append({
            "keyword_no": str(row.get("Keyword No.", "")).strip(),
            "keyword": kw_raw,
            "filters": str(row.get("Filters", "")).strip(),
            "from_date": from_date_val,
            "to_date": to_date_val,
            "abstract": abstract.lower() == "true",
            "freeFullText": freeFullText.lower() == "true",
            "fullText": fullText.lower() == "true",
        })

    if not keywords_memory[project_id]:
        raise HTTPException(status_code=400, detail="No valid keywords found in the uploaded file")

    # Mark search as running
    running_searches[project_id] = True
    cancellation_flags[project_id] = False

    try:
        # Run the pipeline
        inserted = run_pubmed_pipeline(project_id, db, keywords_memory[project_id])
        
        # Clean up
        running_searches[project_id] = False
        
        # Check if cancelled
        if cancellation_flags.get(project_id, False):
            cancellation_flags[project_id] = False
            raise HTTPException(status_code=499, detail="Search cancelled by user")

        return {
            "status": "success",
            "project_id": project_id,
            "records_saved": inserted,
            "message": f"Search completed successfully. {inserted} records saved."
        }

    except HTTPException:
        running_searches[project_id] = False
        raise
    except Exception as e:
        running_searches[project_id] = False
        
        # Try to get partial results count
        try:
            partial_count = db.query(Literature).filter(
                Literature.project_id == project_id
            ).count()
            
            if partial_count > 0:
                return {
                    "status": "partial",
                    "project_id": project_id,
                    "records_saved": partial_count,
                    "message": f"Search encountered errors but saved {partial_count} partial results. Error: {str(e)}"
                }
        except:
            pass
        
        raise HTTPException(status_code=500, detail=f"Literature search failed: {str(e)}")


@router.post("/cancel/{project_id}")
async def cancel_search(project_id: str):
    """Cancel a running literature search"""
    if not running_searches.get(project_id, False):
        raise HTTPException(status_code=404, detail="No active search found for this project")
    
    cancellation_flags[project_id] = True
    
    return {
        "status": "cancelling",
        "project_id": project_id,
        "message": "Search cancellation initiated"
    }


@router.post("/screen")
def run_literature_screening(
    project_id: str = Form(...),
    db: Session = Depends(get_db)
):
    if project_id not in keywords_memory or not keywords_memory[project_id]:
        raise HTTPException(status_code=400, detail="No keywords uploaded for this project")

    try:
        inserted = run_pubmed_pipeline(project_id, db, keywords_memory[project_id])
        return {
            "status": "success",
            "project_id": project_id,
            "records_saved": inserted
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.get("/existing")
def get_existing_literature(
    project_id: int,
    unique_only: bool = True,
    db: Session = Depends(get_db)
):
    query = db.query(Literature).filter(
        Literature.project_id == project_id
    )

    if unique_only:
        query = query.filter(Literature.is_unique == True)

    results = query.all()

    if not results:
        return {
            "exists": False,
            "project_id": project_id,
            "total_records": 0,
            "masterSheet": [],
            "excelFile": None
        }

    df = pd.DataFrame([
        {
            "PMID": r.article_id,
            "Title": r.title,
            "Abstract": r.abstract,
            "Journal": r.journal,
            "Publication Year": r.publication_year,
            "Authors": r.author,
            "Source": r.source,
            "Keyword No.": r.keyword_id,
            "Is Unique": r.is_unique
        }
        for r in results
    ])

    # Create Excel file and encode as base64
    excel_buffer = BytesIO()
    with pd.ExcelWriter(excel_buffer, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="All-Merged")
    
    excel_buffer.seek(0)
    excel_base64 = base64.b64encode(excel_buffer.read()).decode('utf-8')

    return {
        "exists": True,
        "project_id": project_id,
        "total_records": len(df),
        "masterSheet": df.fillna("").to_dict(orient="records"),
        "excelFile": excel_base64
    }


@router.get("/export")
def export_literature_results(
    project_id: int,
    export_type: str = "unique",  # unique | all | duplicates
    db: Session = Depends(get_db)
):
    query = db.query(Literature).filter(
        Literature.project_id == project_id
    )

    if export_type == "unique":
        query = query.filter(Literature.is_unique == True)
    elif export_type == "duplicates":
        query = query.filter(Literature.is_unique == False)
    elif export_type == "all":
        pass
    else:
        raise HTTPException(status_code=400, detail="Invalid export_type")

    results = query.all()
    if not results:
        raise HTTPException(status_code=404, detail="No literature results found")

    df = pd.DataFrame([
        {
            "Keyword No.": r.keyword_id,
            "PMID": r.article_id,
            "Title": r.title,
            "Abstract": r.abstract,
            "Journal": r.journal,
            "Publication Year": r.publication_year,
            "Authors": r.author,
            "Source": r.source,
            "Is Unique": r.is_unique
        }
        for r in results
    ])

    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Literature")

    output.seek(0)

    filename = f"{project_id}_literature_{export_type}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{filename}"'}
    )