from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse
from typing import List
import os
import base64
import shutil
import pandas as pd
import json
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


# ---------------- MODULE 1.1: GET EXISTING PDF DOWNLOAD ----------------
@router.get("/pdf-download/existing")
def get_existing_pdf_download(project_id: str):
    output_path = f"database/{project_id}/secondary/output/pdf_download_status.xlsx"

    if not os.path.exists(output_path):
        return {"exists": False}

    df = pd.read_excel(output_path).fillna("")

    # Normalize PMID (remove .0)
    if "PMID" in df.columns:
        df["PMID"] = df["PMID"].astype(str).str.replace(".0", "", regex=False)

    required_cols = ["PMID", "PMCID", "PDF_Link", "Status"]
    df = df[[c for c in required_cols if c in df.columns]]

    with open(output_path, "rb") as f:
        excel_bytes = f.read()

    return {
        "exists": True,
        "screening": df.to_dict(orient="records"),
        "excelFile": base64.b64encode(excel_bytes).decode(),
    }



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
                "pmid": os.path.splitext(file)[0].replace(".0", "")
            })

    return {"pdfs": pdfs}



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
        raise HTTPException(status_code=404, detail="PDF not found")

    return FileResponse(
        pdf_path,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f'inline; filename="{filename}"'
        }
    )


# ---------------- MODULE 2: PDF → TEXT (OPTIMIZED) ----------------
@router.post("/pdf-to-text")
async def pdf_to_text(
    project_id: str = Form(...),
    selected_pmids: str = Form(None)  # JSON array of selected PMIDs
):
    project_folder = os.path.join("database", project_id, "secondary")
    pdf_folder = os.path.join(project_folder, "pdf")
    text_folder = os.path.join(project_folder, "text")

    if not os.path.exists(pdf_folder):
        raise HTTPException(status_code=404, detail="PDF folder does not exist")

    # Parse selected PMIDs (optional - for future optimization)
    pmid_list = None
    if selected_pmids:
        try:
            pmid_list = json.loads(selected_pmids)
        except:
            pass


    return run_pdf_to_text(pdf_dir=pdf_folder, text_dir=text_folder)


# ---------------- MODULE 2.1: GET SELECTED PMIDS FOR PROCESSING ----------------
@router.post("/get-selected-data")
async def get_selected_data(
    project_id: str = Form(...),
    selected_pmids: str = Form(...)  # JSON array of PMIDs
):
    """
    Filter and return only selected PMID records for further processing
    """
    try:
        pmid_list = json.loads(selected_pmids)
        
        output_path = f"database/{project_id}/secondary/output/pdf_download_status.xlsx"
        
        if not os.path.exists(output_path):
            raise HTTPException(status_code=404, detail="PDF download data not found")
        
        df = pd.read_excel(output_path).fillna("")
        
        # Normalize PMID
        if "PMID" in df.columns:
            df["PMID"] = df["PMID"].astype(str).str.replace(".0", "", regex=False)
        
        # Filter only selected PMIDs
        filtered_df = df[df["PMID"].isin(pmid_list)]
        
        # Calculate stats
        total = len(filtered_df)
        available = len(filtered_df[filtered_df["Status"].str.contains("Available", case=False, na=False)])
        unavailable = total - available
        
        return {
            "status": "success",
            "total": total,
            "available": available,
            "unavailable": unavailable,
            "records": filtered_df.to_dict(orient="records")
        }
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid PMID list format")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# ---------------- MODULE 3: SECONDARY RUNNER (OPTIMIZED) ----------------
@router.post("/secondary-runner")
async def secondary_runner(
    project_id: str = Form(...),
    ifu_pdf: UploadFile = File(...),
    primary_excel: UploadFile = File(...),
    selected_pmids: str = Form(None)  # JSON array of selected PMIDs
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

    # Parse selected PMIDs (optional - for future optimization)
    pmid_list = None
    if selected_pmids:
        try:
            pmid_list = json.loads(selected_pmids)
            # If PMIDs are selected, filter the primary Excel before processing
            if pmid_list and len(pmid_list) > 0:
                df_primary = pd.read_excel(primary_path)
                # Normalize PMID column if it exists
                if "PMID" in df_primary.columns:
                    df_primary["PMID"] = df_primary["PMID"].astype(str).str.replace(".0", "", regex=False)
                    # Filter only selected PMIDs
                    df_primary = df_primary[df_primary["PMID"].isin(pmid_list)]
                    # Save filtered data
                    filtered_path = os.path.join(input_folder, "primary_screening_filtered.xlsx")
                    df_primary.to_excel(filtered_path, index=False)
                    primary_path = filtered_path
        except:
            pass

  
    output_excel = run_secondary_screening(
        primary_excel_path=primary_path,
        ifu_pdf_path=ifu_path,
        text_dir=text_folder,
        output_dir=output_folder
    )

    with open(output_excel, "rb") as f:
        encoded = base64.b64encode(f.read()).decode()

    return {"status": "success", "excelFile": encoded}


@router.get("/existing")
def get_existing_secondary(project_id: str):
    output_path = f"database/{project_id}/secondary/output/secondary_results.xlsx"

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