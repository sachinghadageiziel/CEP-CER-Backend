from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import pandas as pd
from io import BytesIO
from fastapi import Form


from db.database import get_db
from secondary.pdf_download_runner import run_pdf_download

from secondary.secondary_runner import run_secondary_screening_db
from db.models.secondary_screening_model import SecondaryScreening



router = APIRouter(
    prefix="/api/secondary",
    tags=["Secondary Screening"]
)

# =====================================================
# 1️ DOWNLOAD PDFs (PubMed + Included only)
# =====================================================
@router.post("/download-pdfs/{project_id}")
def download_pdfs(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Downloads PDFs ONLY for:
    - source = PubMed
    - primary decision = include

    All other literature → status = pending
    """

    try:
        return run_pdf_download(db=db, project_id=project_id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# =====================================================
# 2️ CHECK PDF DOWNLOAD STATUS
# =====================================================
@router.get("/pdf-status/{project_id}")
def get_pdf_status(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Returns download status of all literature PDFs
    """

    rows = (
        db.query(PdfDownloadStatus)
        .filter(PdfDownloadStatus.project_id == project_id)
        .all()
    )

    return {
        "exists": bool(rows),
        "total": len(rows),
        "data": [
            {
                "literature_id": r.literature_id,
                "status": r.status,          # pending | downloaded | not_found | failed
                "pmcid": r.pmcid,
                "pdf_url": r.pdf_url,
                "file_path": r.file_path,
                "error": r.error_message
            }
            for r in rows
        ]
    }


# =====================================================
# 3️ RUN SECONDARY SCREENING (DB → DB)
# =====================================================
@router.post("/secondary-screen/{project_id}")
def run_secondary_screening(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Runs secondary screening using:
    - IFU from Project table
    - Included Primary Screening records
    - Stores results in secondary_screening table
    """

    try:
        processed = run_secondary_screening_db(
            db=db,
            project_id=project_id
        )

        return {
            "status": "success",
            "project_id": project_id,
            "processed_articles": processed
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# 4️ GET SECONDARY SCREENING RESULTS
# =====================================================
@router.get("/secondary-screen/{project_id}")
def get_secondary_results(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Fetch secondary screening results for a project
    """

    rows = (
        db.query(SecondaryScreening)
        .filter(SecondaryScreening.project_id == project_id)
        .all()
    )

    if not rows:
        return {
            "exists": False,
            "project_id": project_id,
            "total": 0,
            "data": []
        }

    return {
        "exists": True,
        "project_id": project_id,
        "total": len(rows),
        "data": [
            {
                "literature_id": r.literature_id,
                "summary": r.summary,
                "study_type": r.study_type,
                "device": r.device,
                "sample_size": r.sample_size,

                "appropriate_device": r.appropriate_device,
                "appropriate_device_application": r.appropriate_device_application,
                "appropriate_patient_group": r.appropriate_patient_group,
                "acceptable_report": r.acceptable_report,

                "suitability_score": r.suitability_score,
                "data_contribution_score": r.data_contribution_score,

                "data_source_type": r.data_source_type,
                "outcome_measures": r.outcome_measures,
                "follow_up": r.follow_up,
                "statistical_significance": r.statistical_significance,
                "clinical_significance": r.clinical_significance,

                "number_of_males": r.number_of_males,
                "number_of_females": r.number_of_females,
                "mean_age": r.mean_age,

                "result": r.result,
                "rationale": r.rationale,
            }
            for r in rows
        ]
    }


# =====================================================
# 5️ EXPORT SECONDARY SCREENING RESULTS AS EXCEL
# =====================================================
@router.get("/export-secondary-screen/{project_id}")
def export_secondary_results_excel(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Export secondary screening results as Excel
    """

    rows = (
        db.query(SecondaryScreening)
        .filter(SecondaryScreening.project_id == project_id)
        .all()
    )

    if not rows:
        raise HTTPException(
            status_code=404,
            detail="No secondary screening results found for this project"
        )

    # Convert DB rows to list of dicts
    data = [
        {
            "Literature ID": r.literature_id,
            "Summary": r.summary,
            "Study Type": r.study_type,
            "Device": r.device,
            "Sample Size": r.sample_size,

            "Appropriate Device": r.appropriate_device,
            "Appropriate Device Application": r.appropriate_device_application,
            "Appropriate Patient Group": r.appropriate_patient_group,
            "Acceptable Report": r.acceptable_report,

            "Suitability Score": r.suitability_score,
            "Data Contribution Score": r.data_contribution_score,

            "Data Source Type": r.data_source_type,
            "Outcome Measures": r.outcome_measures,
            "Follow Up": r.follow_up,
            "Statistical Significance": r.statistical_significance,
            "Clinical Significance": r.clinical_significance,

            "Number of Males": r.number_of_males,
            "Number of Females": r.number_of_females,
            "Mean Age": r.mean_age,

            "Result": r.result,
            "Rationale": r.rationale,
        }
        for r in rows
    ]

    df = pd.DataFrame(data)

    # Create Excel in-memory
    output = BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Secondary Screening")

    output.seek(0)

    filename = f"secondary_screening_project_{project_id}.xlsx"

    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={filename}"
        }
    )

# =====================================================
# 6 UPDATE SECONDARY SCREENING (Result & Rationale)
# =====================================================
@router.put("/secondary-screen/{project_id}/{literature_id}")
def update_secondary_screening_result(
    project_id: int,
    literature_id: int,
    result: str = Form(...),
    rationale: str | None = Form(None),
    db: Session = Depends(get_db)
):
    screening = (
        db.query(SecondaryScreening)
        .filter(
            SecondaryScreening.project_id == project_id,
            SecondaryScreening.literature_id == literature_id
        )
        .first()
    )

    if not screening:
        raise HTTPException(
            status_code=404,
            detail="Secondary screening record not found"
        )

    screening.result = result
    screening.rationale = rationale

    db.commit()
    db.refresh(screening)

    return {
        "status": "success",
        "project_id": project_id,
        "literature_id": literature_id,
        "message": "Secondary screening updated successfully"
    }


# =====================================================
# 7 DELETE SECONDARY SCREENING RECORD
# =====================================================
@router.delete("/secondary-screen/{project_id}/{literature_id}")
def delete_secondary_screening(
    project_id: int,
    literature_id: int,
    db: Session = Depends(get_db)
):
    screening = (
        db.query(SecondaryScreening)
        .filter(
            SecondaryScreening.project_id == project_id,
            SecondaryScreening.literature_id == literature_id
        )
        .first()
    )

    if not screening:
        raise HTTPException(
            status_code=404,
            detail="Secondary screening record not found"
        )

    db.delete(screening)
    db.commit()

    return {
        "status": "success",
        "project_id": project_id,
        "literature_id": literature_id,
        "message": "Secondary screening record deleted successfully"
    }
