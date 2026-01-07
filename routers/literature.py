from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from io import BytesIO
import pandas as pd

from db.database import get_db
from db.models import LiteratureKeyword  #  UPDATED IMPORT
from literature.pubmed_runner import run_pubmed_pipeline
from db.models.literature_results_model import LiteratureResult


router = APIRouter(
    prefix="/api/literature",
    tags=["Literature Screening"]
)


@router.post("/upload-keywords")
async def upload_keywords(
    project_id: str = Form(...),
    keywordsFile: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    #  ALWAYS read file as bytes first
    file_bytes = await keywordsFile.read()

    if not file_bytes:
        raise HTTPException(status_code=400, detail="Empty file uploaded")

    #  Read Excel safely
    try:
        df = pd.read_excel(BytesIO(file_bytes))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid Excel file: {str(e)}"
        )

    # Normalize column names
    df.columns = [c.strip() for c in df.columns]

    # Required columns
    required_cols = ["Keyword No.", "Keywords"]
    for col in required_cols:
        if col not in df.columns:
            raise HTTPException(
                status_code=400,
                detail=f"Missing required column: {col}"
            )

    inserted = 0

    # Optional: remove old keywords for same project
    db.query(LiteratureKeyword).filter(
        LiteratureKeyword.project_id == project_id
    ).delete()

    # Insert rows
    for _, row in df.iterrows():
        keyword = LiteratureKeyword(
            project_id=project_id,
            keyword_no=str(row.get("Keyword No.", "")).strip(),
            keyword=str(row.get("Keywords", "")).strip(),
            filters=str(row.get("Filters", "")).strip(),
            date_range=str(row.get("Date Range", "")).strip(),
        )
        db.add(keyword)
        inserted += 1

    db.commit()

    return {
        "status": "success",
        "project_id": project_id,
        "keywords_inserted": inserted
    }


@router.post("/screen")
def run_literature_screening(
    project_id: str,
    db: Session = Depends(get_db)
):
    try:
        inserted = run_pubmed_pipeline(project_id, db)

        return {
            "status": "success",
            "project_id": project_id,
            "records_saved": inserted
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
@router.get("/existing")
def get_existing_literature(
    project_id: str,
    db: Session = Depends(get_db)
):
    results = (
        db.query(LiteratureResult)
        .filter(LiteratureResult.project_id == project_id)
        .all()
    )

    if not results:
        return {
            "exists": False,
            "project_id": project_id,
            "masterSheet": []
        }

    df = pd.DataFrame([
        {
            "PMID": r.pmid,
            "Title": r.title,
            "Abstract": r.abstract,
            "Journal": r.journal,
            "Publication Year": r.publication_year,  # ✅ FIXED
            "Authors": r.authors,
            "Source": r.source,
            "Keyword ID": r.keyword_id,
        }
        for r in results
    ])

    return {
        "exists": True,
        "project_id": project_id,
        "total_records": len(df),
        "masterSheet": df.fillna("").to_dict(orient="records")
    }

