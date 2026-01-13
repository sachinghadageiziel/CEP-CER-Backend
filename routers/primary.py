from fastapi import APIRouter, Form, Depends, HTTPException
from sqlalchemy.orm import Session
import os
from fastapi.responses import StreamingResponse
from io import BytesIO
import pandas as pd
from db.database import get_db
from db.models.project_model import Project
from db.models.primary_screening_model import PrimaryScreening
from services.primary_screening_service import run_primary_screening_for_project

router = APIRouter(prefix="/api/primary", tags=["Primary Screening"])


@router.post("/primary-screen")
def run_primary(
    project_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """
    Runs primary screening using the IFU stored in the database
    """

    # -------------------------------------------------
    # 1. Validate project
    # -------------------------------------------------
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project:
        raise HTTPException(status_code=404, detail="Project not found")

    # -------------------------------------------------
    # 2. Validate IFU in DB
    # -------------------------------------------------
    if not project.ifu_file_data:
        raise HTTPException(
            status_code=400,
            detail="IFU not found for this project. Upload IFU while creating project."
        )

    # -------------------------------------------------
    # 3. Run primary screening (DB IFU)
    # -------------------------------------------------
    screened = run_primary_screening_for_project(
        db=db,
        project_id=project_id,
        ifu_bytes=project.ifu_file_data
    )

    return {
        "status": "success",
        "project_id": project_id,
        "screened_articles": screened
    }


@router.get("/primary-screen")
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


@router.get("/export-primary-screen")
def export_primary_screen(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Export primary screening results as Excel
    """

    results = (
        db.query(PrimaryScreening)
        .filter(PrimaryScreening.project_id == project_id)
        .all()
    )

    if not results:
        raise HTTPException(
            status_code=404,
            detail="No primary screening results found"
        )

    # Create DataFrame
    df = pd.DataFrame([
        {
            "Literature ID (PMID)": r.literature_id,
            "Decision": r.decision,
            "Exclusion Criteria": r.exclusion_criteria,
            "Rationale": r.rationale
        }
        for r in results
    ])

    # Write to Excel
    output = BytesIO()
    with pd.ExcelWriter(output, engine="xlsxwriter") as writer:
        df.to_excel(writer, index=False, sheet_name="Primary Screening")

    output.seek(0)

    filename = f"{project_id}_primary_screening.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f'attachment; filename="{filename}"'
        }
    )


# =====================================================
# UPDATE PRIMARY SCREENING (Decision & Rationale)
# =====================================================
@router.put("/{project_id}/{literature_id}")
def update_primary_screening(
    project_id: int,
    literature_id: str,
    decision: str = Form(...),
    rationale: str | None = Form(None),
    db: Session = Depends(get_db)
):
    screening = (
        db.query(PrimaryScreening)
        .filter(
            PrimaryScreening.project_id == project_id,
            PrimaryScreening.literature_id == literature_id
        )
        .first()
    )

    if not screening:
        raise HTTPException(
            status_code=404,
            detail="Primary screening record not found"
        )

    screening.decision = decision
    screening.rationale = rationale

    db.commit()
    db.refresh(screening)

    return {
        "status": "success",
        "project_id": project_id,
        "literature_id": literature_id,
        "message": "Primary screening updated successfully"
    }


# =====================================================
# DELETE PRIMARY SCREENING
# =====================================================
@router.delete("/{project_id}/{literature_id}")
def delete_primary_screening(
    project_id: int,
    literature_id: str,
    db: Session = Depends(get_db)
):
    screening = (
        db.query(PrimaryScreening)
        .filter(
            PrimaryScreening.project_id == project_id,
            PrimaryScreening.literature_id == literature_id
        )
        .first()
    )

    if not screening:
        raise HTTPException(
            status_code=404,
            detail="Primary screening record not found"
        )

    db.delete(screening)
    db.commit()

    return {
        "status": "success",
        "project_id": project_id,
        "literature_id": literature_id,
        "message": "Primary screening record deleted successfully"
    }
