from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
from io import BytesIO
import pandas as pd
from datetime import datetime

from db.database import get_db
from literature.pubmed_runner import run_pubmed_pipeline
from db.models.literature_model import Literature

# -------------------------------
# In-memory store for uploaded keywords (per project)
keywords_memory = {}
# -------------------------------

router = APIRouter(
    prefix="/api/literature",
    tags=["Literature Screening"]
)


@router.post("/keywords")
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


@router.post("/literature-screen")
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


@router.get("/literature-screen")
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
            "masterSheet": []
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

    return {
        "exists": True,
        "project_id": project_id,
        "total_records": len(df),
        "masterSheet": df.fillna("").to_dict(orient="records")
    }



@router.get("/export-literature-screen")
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


# =====================================================
# UPDATE LITERATURE RECORD
# =====================================================
@router.put("/{project_id}/{pmid}")
def update_literature(
    project_id: int,
    pmid: str,
    title: str | None = Form(None),
    abstract: str | None = Form(None),
    journal: str | None = Form(None),
    publication_year: int | None = Form(None),
    authors: str | None = Form(None),
    is_unique: bool | None = Form(None),
    db: Session = Depends(get_db)
):
    literature = (
        db.query(Literature)
        .filter(
            Literature.project_id == project_id,
            Literature.article_id == pmid
        )
        .first()
    )

    if not literature:
        raise HTTPException(status_code=404, detail="Literature record not found")

    # Update fields only if provided
    if title is not None:
        literature.title = title

    if abstract is not None:
        literature.abstract = abstract

    if journal is not None:
        literature.journal = journal

    if publication_year is not None:
        literature.publication_year = publication_year

    if authors is not None:
        literature.author = authors

    if is_unique is not None:
        literature.is_unique = is_unique

    db.commit()
    db.refresh(literature)

    return {
        "status": "success",
        "project_id": project_id,
        "pmid": pmid,
        "message": "Literature record updated successfully"
    }


# =====================================================
# DELETE LITERATURE RECORD
# =====================================================
@router.delete("/{project_id}/{pmid}")
def delete_literature(
    project_id: int,
    pmid: str,
    db: Session = Depends(get_db)
):
    literature = (
        db.query(Literature)
        .filter(
            Literature.project_id == project_id,
            Literature.article_id == pmid
        )
        .first()
    )

    if not literature:
        raise HTTPException(status_code=404, detail="Literature record not found")

    db.delete(literature)
    db.commit()

    return {
        "status": "success",
        "project_id": project_id,
        "pmid": pmid,
        "message": "Literature record deleted successfully"
    }
