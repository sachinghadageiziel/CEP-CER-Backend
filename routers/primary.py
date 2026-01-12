from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
import os

from db.database import get_db
from db.models.primary_screening_model import PrimaryScreening
from services.primary_screening_service import run_primary_screening_for_project

router = APIRouter(prefix="/api/primary", tags=["Primary Screening"])


@router.post("/run")
async def run_primary(
    project_id: int = Form(...),
    ifu_pdf: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Runs primary screening ONCE per unique literature article
    """

    project_folder = f"database/{project_id}/primary"
    os.makedirs(project_folder, exist_ok=True)

    ifu_path = f"{project_folder}/IFU.pdf"
    with open(ifu_path, "wb") as f:
        f.write(await ifu_pdf.read())

    screened = run_primary_screening_for_project(
        db=db,
        project_id=project_id,
        ifu_pdf_path=ifu_path
    )

    return {
        "status": "success",
        "project_id": project_id,
        "screened_articles": screened
    }


@router.get("/existing")
def get_existing_primary(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Fetch already completed primary screening results from DB
    """

    results = (
        db.query(PrimaryScreening)
        .filter(PrimaryScreening.project_id == project_id)
        .all()
    )

    return {
        "exists": bool(results),
        "total": len(results),
        "data": [
            {
                "literature_id": r.literature_id,
                "decision": r.decision,
                "exclusion_criteria": r.exclusion_criteria,
                "rationale": r.rationale,
            }
            for r in results
        ]
    }
