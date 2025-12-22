from fastapi import APIRouter, UploadFile, File, Form
import os
import base64
import shutil

from secondary.pdf_download_runner import run_pdf_download
from secondary.pdf_to_text_runner import run_pdf_to_text
from secondary.secondary_runner import run_secondary_screening

router = APIRouter(prefix="/api/secondary", tags=["Secondary Screening"])


# ---------------- MODULE 1 ----------------
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


# ---------------- MODULE 2 ----------------
@router.post("/pdf-to-text")
async def pdf_to_text(project_id: str = Form(...)):
    project_folder = os.path.join("database", project_id, "secondary")
    pdf_folder = os.path.join(project_folder, "pdf")
    text_folder = os.path.join(project_folder, "text")

    if not os.path.exists(pdf_folder):
        return {"status": "error", "message": "PDF folder does not exist"}

    return run_pdf_to_text(pdf_dir=pdf_folder, text_dir=text_folder)


# ---------------- MODULE 3 ----------------
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

    # ✅ FIXED: Save IFU PDF (binary safe)
    ifu_path = os.path.join(input_folder, "ifu.pdf")
    with open(ifu_path, "wb") as buffer:
        shutil.copyfileobj(ifu_pdf.file, buffer)

    # ✅ FIXED: Save Primary Excel (binary safe)
    primary_path = os.path.join(input_folder, "primary_screening.xlsx")
    with open(primary_path, "wb") as buffer:
        shutil.copyfileobj(primary_excel.file, buffer)

    # ✅ Correct argument order
    output_excel = run_secondary_screening(
        primary_excel_path=primary_path,
        ifu_pdf_path=ifu_path,
        text_dir=text_folder,
        output_dir=output_folder
    )

    with open(output_excel, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    return {"status": "success", "excelFile": encoded}
