from fastapi import APIRouter, UploadFile, File, Form
import os
import base64
import pandas as pd

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

    return {
        "status": "success",
        "excelFile": encoded
    }


@router.get("/existing")
def get_existing_primary(project_id: str):
    """
    Check if primary screening result already exists.
    Returns parsed Excel + base64 file.
    """

    output_path = f"database/{project_id}/primary/screening_results.xlsx"

    if not os.path.exists(output_path):
        return {"exists": False}

    df = pd.read_excel(output_path).fillna("")

    with open(output_path, "rb") as f:
        excel_bytes = f.read()

    return {
        "exists": True,
        "masterSheet": df.to_dict(orient="records"),
        "excelFile": base64.b64encode(excel_bytes).decode(),
    }



#MyChanges KB

@router.get("/article")
def get_primary_article(project_id: str, pmid: str):
    path = f"database/{project_id}/primary/screening_results.xlsx"
    if not os.path.exists(path):
        return {"found": False}

    df = pd.read_excel(path).fillna("")
    row = df[df["PMID"].astype(str) == str(pmid)]

    if row.empty:
        return {"found": False}

    return {
        "found": True,
        "article": row.iloc[0].to_dict()
    }


@router.post("/decision")
def update_decision(
    project_id: str = Form(...),
    pmid: str = Form(...),
    decision: str = Form(...),
    reason: str = Form("")
):
    path = f"database/{project_id}/primary/screening_results.xlsx"
    df = pd.read_excel(path).fillna("")

    idx = df[df["PMID"].astype(str) == str(pmid)].index
    if len(idx) == 0:
        return {"updated": False}

    df.loc[idx, "Decision"] = decision
    df.loc[idx, "OverrideReason"] = reason

    df.to_excel(path, index=False)
    return {"updated": True}


@router.get("/page")
def get_primary_page(
    project_id: str,
    page: int = 1,
    size: int = 20
):
    path = f"database/{project_id}/primary/screening_results.xlsx"
    df = pd.read_excel(path).fillna("")

    start = (page - 1) * size
    end = start + size

    return {
        "total": len(df),
        "page": page,
        "size": size,
        "rows": df.iloc[start:end].to_dict(orient="records")
    }
