from fastapi import APIRouter, UploadFile, File, Form
import os
import base64
from secondary.pipeline.run_secondary_pipeline import run_secondary_pipeline

router = APIRouter(prefix="/api/secondary", tags=["Secondary Screening"])


@router.post("/run")
async def secondary_screening(
    project_id: str = Form(...),
    working_file: UploadFile = File(...),
    ifu_file: UploadFile = File(...)
):
    """
    Upload working.xlsx and ifu.pdf for a project.
    Saves files in database/{project_id}/secondary/
    Runs the full secondary screening pipeline.
    Returns base64 encoded result.xlsx
    """

    # Create project secondary folder if not exists
    project_folder = os.path.join("database", project_id, "secondary")
    os.makedirs(project_folder, exist_ok=True)

    # Save working.xlsx
    working_path = os.path.join(project_folder, "working.xlsx")
    with open(working_path, "wb") as f:
        f.write(await working_file.read())

    # Save ifu.pdf
    ifu_path = os.path.join(project_folder, "ifu.pdf")
    with open(ifu_path, "wb") as f:
        f.write(await ifu_file.read())

    # Run pipeline
    result_excel = run_secondary_pipeline(project_id)

    # Return result as base64
    with open(result_excel, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    return {
        "status": "success",
        "excelFile": encoded
    }
