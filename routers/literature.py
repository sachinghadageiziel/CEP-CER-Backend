from fastapi import APIRouter, UploadFile, File, Form
import os
import base64
import pandas as pd

from services.project_paths import ensure_project_folders
from literature.pubmed_runner import run_pubmed_pipeline

router = APIRouter(prefix="/api/literature", tags=["Literature Screening"])


@router.post("/run")
async def run_pipeline(
    project_id: str = Form(...),
    keywordsFile: UploadFile = File(...),
    applyDateFilter: str = Form("false"),
    fromDate: str = Form(""),
    toDate: str = Form(""),
    abstract: str = Form("false"),
    freeFullText: str = Form("false"),
    fullText: str = Form("false"),
):

    paths = ensure_project_folders(project_id)
    literature_folder = paths["literature"]

    # Save uploaded keywords file inside correct folder
    keywords_path = os.path.join(literature_folder, "keywords.xlsx")
    with open(keywords_path, "wb") as f:
        f.write(await keywordsFile.read())

    # Convert string to boolean
    def to_bool(v):
        return v.lower() == "true"

    params = {
        "applyDateFilter": to_bool(applyDateFilter),
        "fromDate": fromDate,
        "toDate": toDate,
        "abstract": to_bool(abstract),
        "freeFullText": to_bool(freeFullText),
        "fullText": to_bool(fullText),
    }

    # Run pipeline and save Excel inside literature/
    excel_path = run_pubmed_pipeline(
        keywords_path,
        literature_folder,
        params,
        project_id
    )

    # Return as base64
    with open(excel_path, "rb") as f:
        excel_bytes = f.read()

    return {
        "status": "success",
        "excelFile": base64.b64encode(excel_bytes).decode()
    }


@router.get("/existing")
def get_existing(project_id: str):
    master_path = f"database/{project_id}/literature/All-Merged.xlsx"

    if not os.path.exists(master_path):
        return {"exists": False}

    df = pd.read_excel(master_path).fillna("")

    with open(master_path, "rb") as f:
        excel_bytes = f.read()

    return {
        "exists": True,
        "masterSheet": df.to_dict(orient="records"),
        "excelFile": base64.b64encode(excel_bytes).decode(),
    }
