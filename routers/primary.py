from fastapi import APIRouter, UploadFile, File, Form, Depends
from sqlalchemy.orm import Session
import os

from db.database import get_db
from db.models.project_model import Project
from db.models.primary_screening_model import PrimaryScreening
from services.primary_screening_service import run_primary_screening_for_project

router = APIRouter(prefix="/api/primary", tags=["Primary Screening"])


@router.post("/run")
def run_primary(
    project_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """
    Runs primary screening using the IFU stored at project level
    """

    # -------------------------------------------------
    # 1. Validate project
    # -------------------------------------------------
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # -------------------------------------------------
    # 2. Load IFU from project folder
    # -------------------------------------------------
    ifu_path = f"database/projects/{project_id}/IFU.pdf"

    if not os.path.exists(ifu_path):
        raise HTTPException(
            status_code=400,
            detail="IFU not found for this project. Upload IFU while creating project."
        )

    # -------------------------------------------------
    # 3. Run primary screening
    # -------------------------------------------------
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
