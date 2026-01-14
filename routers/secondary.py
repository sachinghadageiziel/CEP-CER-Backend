from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.database import get_db
from secondary.pdf_download_runner import run_pdf_download


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


