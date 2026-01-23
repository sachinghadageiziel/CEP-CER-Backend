import os
import requests
import pandas as pd
import json
import ast
import re
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from io import BytesIO
from PyPDF2 import PdfReader

load_dotenv()
API_URL = os.getenv("PRIMARY_API_URL", "http://localhost:7860/api/v1/run/primaryscreen-1-1-1-1")
API_KEY = os.getenv("PRIMARY_API_KEY")


def read_ifu_from_bytes(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    text = [page.extract_text() or "" for page in reader.pages]
    return "\n".join(text).strip()
    


def clean_json_text(text: str) -> str:
    text = re.sub(r"^```json", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"^```", "", text.strip(), flags=re.MULTILINE)
    return text.strip("` \n\t")


def safe_parse_json(text: str) -> dict:
    """
    Tries strict JSON first, then Python-dict fallback.
    Prevents: name 'json' is not defined
    """
    try:
        return json.loads(text)
    except Exception:
        try:
            return ast.literal_eval(text)
        except Exception as e:
            raise ValueError(f"Parse error: {e}")


def call_langflow(ifu: str, abstract: str):
    headers = {"Content-Type": "application/json", "x-api-key": API_KEY}
    payload = {
        "output_type": "chat",
        "input_type": "text",
        "input_value": abstract,
        "tweaks": {"Prompt-QH9TX": {"ifu_text": ifu, "abstract_text": abstract}},
    }
    try:
        response = requests.post(API_URL, json=payload, headers=headers)
        response.raise_for_status()
        return response.json()
    except Exception as e:
        return {"Decision": "ERROR", "Rationale": str(e)}


def run_primary_screening(input_excel_path: str, ifu_pdf_path: str, output_folder: str, sheet_name="Master") -> str:
    """
    input_excel_path : path to All-Merged.xlsx
    ifu_pdf_path    : path to IFU.pdf
    output_folder   : folder to save results (database/PRJ-XXX/primary)
    Returns path to output Excel
    """

    os.makedirs(output_folder, exist_ok=True)
    ifu_text = read_ifu_from_pdf(ifu_pdf_path)
    df = pd.read_excel(input_excel_path, sheet_name=sheet_name)

    if "Abstract" not in df.columns:
        raise ValueError("Excel must contain an 'Abstract' column")

    results = []

    for _, row in df.iterrows():
        abstract = str(row["Abstract"])
        pmid = row.get("PMID", "")
        result = call_langflow(ifu_text, abstract)

        if "outputs" in result:
            try:
                msg = result["outputs"][0]["outputs"][0]["results"]["message"]

                if "data" in msg and "text" in msg["data"]:
                    text_out = msg["data"]["text"]
                elif "text" in msg:
                    text_out = msg["text"]
                else:
                    raise ValueError(f"No 'text' field found in message: {msg}")

                clean_text = clean_json_text(text_out)
                result = safe_parse_json(clean_text)

            except Exception as e:
                result = {
                    "Decision": "ERROR",
                    "Category": "NA",
                    "ExcludedCriteria": "NA",
                    "Rationale": str(e),
                }

        record = {
            "PMID": pmid,
            "Abstract": abstract,
            "Decision": result.get("Decision", result.get("decision", "")),
            "Category": result.get("Category", result.get("category", "")),
            "ExcludedCriteria": (
                ",".join(result.get("ExcludedCriteria", result.get("excludedCriteria", [])))
                if isinstance(result.get("ExcludedCriteria", result.get("excludedCriteria", "")), list)
                else result.get("ExcludedCriteria", result.get("excludedCriteria", ""))
            ),
            "Rationale": result.get("Rationale", result.get("rationale", "")),
        }

        results.append(record)

    output_excel_path = os.path.join(output_folder, "screening_results.xlsx")
    pd.DataFrame(results).to_excel(output_excel_path, index=False)
    return output_excel_path
