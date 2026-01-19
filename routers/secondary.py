from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session
from fastapi.responses import StreamingResponse
import os
import pandas as pd
from io import BytesIO
from pathlib import Path
from fastapi.responses import FileResponse
import os

from db.database import get_db
from db.models.literature_model import Literature
from db.models.pdf_download_status_model import PdfDownloadStatus
from db.models.secondary_screening_model import SecondaryScreening

from secondary.pdf_download_runner import run_pdf_download, get_system_downloads_dir
from secondary.pdf_to_text_runner import run_pdf_to_text
from secondary.secondary_runner import run_secondary_screening_db
from secondary.secondary_runner import run_secondary_screening_selected_db


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
    including article_id
    """

    rows = (
        db.query(PdfDownloadStatus, Literature)
        .join(
            Literature,
            PdfDownloadStatus.literature_id == Literature.id
        )
        .filter(PdfDownloadStatus.project_id == project_id)
        .all()
    )

    return {
        "exists": bool(rows),
        "total": len(rows),
        "data": [
            {
                "literature_id": pdf.literature_id,
                "article_id": lit.article_id,  
                "status": pdf.status,
                "pmcid": pdf.pmcid,
                "pdf_url": pdf.pdf_url,
                "file_path": pdf.file_path,
                "error": pdf.error_message
            }
            for pdf, lit in rows
        ]
    }

@router.post("/upload-pdf/{project_id}/{literature_id}")
def upload_pdf(
    project_id: int,
    literature_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db)
):
    """
    Manually upload PDF for a literature entry.
    - Always replaces the existing PDF (if any) and regenerates the text file.
    - Saves file as <article_id>.pdf
    """

    # ------------------------
    # 1️ Fetch PDF status
    # ------------------------
    pdf_status = (
        db.query(PdfDownloadStatus)
        .filter_by(project_id=project_id, literature_id=literature_id)
        .first()
    )
    if not pdf_status:
        raise HTTPException(status_code=404, detail="PDF status record not found.")

    # ------------------------
    # 2️ Fetch article_id
    # ------------------------
    literature = db.query(Literature).filter(Literature.id == literature_id).first()
    if not literature:
        raise HTTPException(status_code=404, detail="Literature record not found.")
    article_id = literature.article_id

    # ------------------------
    # 3️ Prepare folders
    # ------------------------
    project_folder = os.path.join(get_system_downloads_dir(), f"CEP-CER_Project_{project_id}")
    os.makedirs(project_folder, exist_ok=True)

    text_dir = os.path.join(project_folder, "text")
    os.makedirs(text_dir, exist_ok=True)

    # ------------------------
    # 4️ Save PDF (overwrite if exists)
    # ------------------------
    file_path = os.path.join(project_folder, f"{article_id}.pdf")
    with open(file_path, "wb") as f:
        f.write(file.file.read())

    # ------------------------
    # 5️ Delete old text file if exists
    # ------------------------
    txt_path = os.path.join(text_dir, f"{article_id}.txt")
    if os.path.exists(txt_path):
        os.remove(txt_path)

    # ------------------------
    # 6️ Update DB
    # ------------------------
    pdf_status.file_path = file_path
    pdf_status.status = "Manually downloaded"
    pdf_status.error_message = None
    db.commit()

    # ------------------------
    # 7️ Convert PDF to text
    # ------------------------
    run_pdf_to_text(pdf_dir=project_folder, text_dir=text_dir)

    return {
        "status": "uploaded",
        "file_path": file_path,
        "text_dir": text_dir
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


@router.post("/secondary-screen/selected/{project_id}")
def run_secondary_screening_selected(
    project_id: int,
    literature_ids: list[int] = Form(...),
    db: Session = Depends(get_db)
):
    """
    Run secondary screening ONLY for selected articles
    """

    try:
        processed = run_secondary_screening_selected_db(
            db=db,
            project_id=project_id,
            literature_ids=literature_ids
        )

        return {
            "status": "success",
            "project_id": project_id,
            "processed_articles": processed,
            "selected_articles": literature_ids
        }

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# =====================================================
# 4️ GET SECONDARY SCREENING RESULTS (with article_id)
# =====================================================
@router.get("/secondary-screen/{project_id}")
def get_secondary_results(
    project_id: int,
    db: Session = Depends(get_db)
):
    """
    Fetch secondary screening results for a project
    and include the article_id from Literature table
    """

    rows = (
        db.query(SecondaryScreening, Literature)
        .join(
            Literature,
            SecondaryScreening.literature_id == Literature.id
        )
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
                "article_id": lit.article_id,  # Now accessible
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
            for r, lit in rows  # Unpack tuple from join
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


# =====================================================
# MODULE 1.1: GET EXISTING PDF DOWNLOAD (DB-BASED)
# =====================================================
@router.get("/pdf-download/existing")
def get_existing_pdf_download(project_id: int, db: Session = Depends(get_db)):
    """
    Check if PDF download status exists in database.
    Returns parsed data from pdf_download_status table.
    """
    # Query database for PDF download status
    rows = (
        db.query(PdfDownloadStatus, Literature)
        .join(
            Literature,
            PdfDownloadStatus.literature_id == Literature.id
        )
        .filter(PdfDownloadStatus.project_id == project_id)
        .all()
    )
   
    if not rows:
        return {"exists": False}
   
    # Format data for frontend
    screening_data = [
        {
            "PMID": lit.article_id,  # Using article_id as PMID
            "PMCID": pdf.pmcid or "",
            "PDF_Link": pdf.pdf_url or "",
            "Status": pdf.status or "Pending"
        }
        for pdf, lit in rows
    ]
   
    return {
        "exists": True,
        "screening": screening_data,
    }
 
 
 
 
# =====================================================
# MODULE 1.2: LIST DOWNLOADED PDFs (DB-BASED)
# =====================================================
@router.get("/pdf-list")
def list_downloaded_pdfs(project_id: int, db: Session = Depends(get_db)):
    """
    List all downloaded PDFs from database.
    Returns list of PDFs with their metadata.
    """
    rows = (
        db.query(PdfDownloadStatus, Literature)
        .join(
            Literature,
            PdfDownloadStatus.literature_id == Literature.id
        )
        .filter(
            PdfDownloadStatus.project_id == project_id,
            PdfDownloadStatus.status.in_([
                "Downloaded",
                "Manually downloaded",
                "Successfully downloaded"
            ])
        )
        .all()
    )
   
    if not rows:
        return {"pdfs": []}
   
    pdfs = [
        {
            "filename": f"{lit.article_id}.pdf",
            "pmid": lit.article_id,
            "literature_id": lit.id,
            "file_path": pdf.file_path
        }
        for pdf, lit in rows
        if pdf.file_path and os.path.exists(pdf.file_path)
    ]
   
    return {"pdfs": pdfs}
 
 
# =====================================================
# MODULE 1.3: OPEN PDF (FROM DOWNLOADS)
# =====================================================
@router.get("/open-pdf")
def open_pdf(
    project_id: int,
    filename: str,
    db: Session = Depends(get_db)
):
    """
    Open PDF by filename from system Downloads directory
    using DB metadata.
    """

    # 1️ Extract article_id safely
    article_id = Path(filename).stem

    # 2️ Fetch literature for this project
    literature = (
        db.query(Literature)
        .filter(
            Literature.article_id == article_id,
            Literature.project_id == project_id
        )
        .first()
    )

    if not literature:
        raise HTTPException(status_code=404, detail="Literature record not found")

    # 3️ Fetch PDF status (matches your DB design)
    pdf_status = (
        db.query(PdfDownloadStatus)
        .filter(
            PdfDownloadStatus.project_id == project_id,
            PdfDownloadStatus.literature_id == literature.id
        )
        .first()
    )

    if not pdf_status or not pdf_status.file_path:
        raise HTTPException(status_code=404, detail="PDF not found in database")

    # 4️ Validate file exists on disk
    if not os.path.exists(pdf_status.file_path):
        raise HTTPException(
            status_code=404,
            detail="PDF file not found in Downloads folder"
        )

    # 5️ Stream PDF
    return FileResponse(
        path=pdf_status.file_path,
        media_type="application/pdf",
        filename=filename
    )

 
# =====================================================
# MODULE 2: PDF → TEXT (DB-BASED)
# =====================================================
@router.post("/pdf-to-text")
async def pdf_to_text(
    project_id: int = Form(...),
    db: Session = Depends(get_db)
):
    """
    Convert all downloaded PDFs to text files.
    Uses database records to find PDF locations.
    """
    # Get all downloaded PDFs from database
    pdf_records = (
        db.query(PdfDownloadStatus)
        .filter(
            PdfDownloadStatus.project_id == project_id,
            PdfDownloadStatus.status.in_([
                "Downloaded",
                "Manually downloaded",
                "Successfully downloaded"
            ]),
            PdfDownloadStatus.file_path.isnot(None)
        )
        .all()
    )
   
    if not pdf_records:
        return {
            "status": "error",
            "message": "No downloaded PDFs found in database"
        }
   
    # Setup directories
    project_folder = os.path.join(
        get_system_downloads_dir(),
        f"CEP-CER_Project_{project_id}"
    )
    text_folder = os.path.join(project_folder, "text")
    os.makedirs(text_folder, exist_ok=True)
   
    # Get all PDF file paths
    pdf_files = [
        pdf.file_path for pdf in pdf_records
        if pdf.file_path and os.path.exists(pdf.file_path)
    ]
   
    if not pdf_files:
        return {
            "status": "error",
            "message": "No valid PDF files found on disk"
        }
   
    # Use the directory where PDFs are stored
    pdf_dir = os.path.dirname(pdf_files[0])
   
    return run_pdf_to_text(pdf_dir=pdf_dir, text_dir=text_folder)