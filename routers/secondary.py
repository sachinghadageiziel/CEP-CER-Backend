from fastapi import APIRouter, UploadFile, File, Form
from fastapi.responses import FileResponse
import os
import base64
import shutil

from secondary.pdf_download_runner import run_pdf_download
from secondary.pdf_to_text_runner import run_pdf_to_text
from secondary.secondary_runner import run_secondary_screening

router = APIRouter(prefix="/api/secondary", tags=["Secondary Screening"])


# ---------------- MODULE 1: PDF DOWNLOAD ----------------
@router.post("/pdf-download")
async def pdf_download(
    project_id: str = Form(...),
    pmid_excel: UploadFile = File(...)
):
    project_folder = os.path.join("database", project_id, "secondary")
    input_folder = os.path.join(project_folder, "input")
    output_folder = os.path.join(project_folder, "output")
    pdf_folder = os.path.join(project_folder, "pdf")

    os.makedirs(input_folder, exist_ok=True)
    os.makedirs(output_folder, exist_ok=True)
    os.makedirs(pdf_folder, exist_ok=True)

    excel_path = os.path.join(input_folder, "pmid.xlsx")
    with open(excel_path, "wb") as buffer:
        shutil.copyfileobj(pmid_excel.file, buffer)

    output_excel = run_pdf_download(
        excel_path=excel_path,
        pdf_dir=pdf_folder,
        output_dir=output_folder
    )

    with open(output_excel, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    return {"status": "success", "excelFile": encoded}


# ---------------- MODULE 1.1: LIST DOWNLOADED PDFs ----------------
@router.get("/pdf-list")
def list_downloaded_pdfs(project_id: str):
    pdf_folder = os.path.join("database", project_id, "secondary", "pdf")

    if not os.path.exists(pdf_folder):
        return {"pdfs": []}

    pdfs = []
    for file in os.listdir(pdf_folder):
        if file.lower().endswith(".pdf"):
            pdfs.append({
                "filename": file,
                "pmid": os.path.splitext(file)[0]
            })

    return {"pdfs": pdfs}


# ---------------- MODULE 1.2: OPEN PDF ----------------
@router.get("/open-pdf")
def open_pdf(project_id: str, filename: str):
    pdf_path = os.path.join(
        "database",
        project_id,
        "secondary",
        "pdf",
        filename
    )

    if not os.path.exists(pdf_path):
        return {"error": "PDF not found"}

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        filename=filename
    )


# ---------------- MODULE 2: PDF → TEXT ----------------
@router.post("/pdf-to-text")
async def pdf_to_text(project_id: str = Form(...)):
    project_folder = os.path.join("database", project_id, "secondary")
    pdf_folder = os.path.join(project_folder, "pdf")
    text_folder = os.path.join(project_folder, "text")

    if not os.path.exists(pdf_folder):
        return {"status": "error", "message": "PDF folder does not exist"}

    return run_pdf_to_text(pdf_dir=pdf_folder, text_dir=text_folder)


# ---------------- MODULE 3: SECONDARY RUNNER ----------------
@router.post("/secondary-runner")
async def secondary_runner(
    project_id: str = Form(...),
    ifu_pdf: UploadFile = File(...),
    primary_excel: UploadFile = File(...)
):
    project_folder = os.path.join("database", project_id, "secondary")
    input_folder = os.path.join(project_folder, "input")
    text_folder = os.path.join(project_folder, "text")
    output_folder = os.path.join(project_folder, "output")

    os.makedirs(input_folder, exist_ok=True)
    os.makedirs(text_folder, exist_ok=True)
    os.makedirs(output_folder, exist_ok=True)

    ifu_path = os.path.join(input_folder, "ifu.pdf")
    with open(ifu_path, "wb") as buffer:
        shutil.copyfileobj(ifu_pdf.file, buffer)

    primary_path = os.path.join(input_folder, "primary_screening.xlsx")
    with open(primary_path, "wb") as buffer:
        shutil.copyfileobj(primary_excel.file, buffer)

    output_excel = run_secondary_screening(
        primary_excel_path=primary_path,
        ifu_pdf_path=ifu_path,
        text_dir=text_folder,
        output_dir=output_folder
    )

    with open(output_excel, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    return {"status": "success", "excelFile": encoded}
# ---------------- MODULE 3.1: GET EXISTING SECONDARY ----------------
@router.get("/existing")
def get_existing_secondary(project_id: str):
    """
    Check if secondary screening result already exists.
    Returns parsed Excel + base64 file.
    """
    output_path = f"database/{project_id}/secondary/output/secondary_results.xlsx"

    if not os.path.exists(output_path):
        return {"exists": False}

    import pandas as pd
    import base64

    df = pd.read_excel(output_path).fillna("")

    with open(output_path, "rb") as f:
        excel_bytes = f.read()

    return {
        "exists": True,
        "masterSheet": df.to_dict(orient="records"),
        "excelFile": base64.b64encode(excel_bytes).decode(),
    }