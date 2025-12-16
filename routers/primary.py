from fastapi import APIRouter, UploadFile, File, Form
import os
import base64
from primary.primary_runner import run_primary_screening

router = APIRouter(prefix="/api/primary", tags=["Primary Screening"])

@router.post("/run")
async def primary_screening(
    project_id: str = Form(...),
    all_merged: UploadFile = File(...),
    ifu_pdf: UploadFile = File(...),
):
    """
    Upload All-Merged.xlsx and IFU.pdf for a project.
    Saves files in database/{project_id}/primary/
    Returns base64 encoded Excel results.
    """

    project_folder = os.path.join("database", project_id, "primary")
    os.makedirs(project_folder, exist_ok=True)

    excel_path = os.path.join(project_folder, "All-Merged.xlsx")
    with open(excel_path, "wb") as f:
        f.write(await all_merged.read())

    ifu_path = os.path.join(project_folder, "IFU.pdf")
    with open(ifu_path, "wb") as f:
        f.write(await ifu_pdf.read())

    output_excel = run_primary_screening(excel_path, ifu_path, project_folder)

    with open(output_excel, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    return {"status": "success", "excelFile": encoded}
