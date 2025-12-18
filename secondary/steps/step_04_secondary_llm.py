import os
import json
import re
import requests
import pandas as pd
from PyPDF2 import PdfReader
from dotenv import load_dotenv

load_dotenv()

API_URL = os.getenv(
    "SECONDARY_API_URL",
    "http://localhost:7860/api/v1/run/secondary-screening"
)
API_KEY = os.getenv("SECONDARY_API_KEY")


# -----------------------------
# Helpers
# -----------------------------

def read_ifu(pdf_path):
    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def clean_json(text):
    text = re.sub(r"```json|```", "", text or "")
    return text.strip()


def safe_parse_json(text, pmid):
    try:
        return json.loads(clean_json(text))
    except Exception:
        print(f"[ERROR] Invalid JSON from LLM for PMID={pmid}")
        print("----- LLM OUTPUT START -----")
        print((text or "")[:1000])
        print("----- LLM OUTPUT END -----")
        return None


# -----------------------------
# Main LLM step
# -----------------------------

def run_secondary_screening(excel_path, text_dir, ifu_pdf, output_excel):
    ifu_text = read_ifu(ifu_pdf)

    df = pd.read_excel(excel_path)

    # ✅ Force text columns to string (prevents pandas crash)
    for col in ["Summary", "Rationale"]:
        if col in df.columns:
            df[col] = df[col].astype(str)

    for file in os.listdir(text_dir):
        if not file.endswith(".txt"):
            continue

        pmid = file.replace(".txt", "")

        if pmid not in df["PMID"].astype(str).values:
            continue

        txt_path = os.path.join(text_dir, file)
        with open(txt_path, encoding="utf-8", errors="ignore") as f:
            article = f.read().strip()

        print(f"[INFO] PMID={pmid}, article length={len(article)}")

        # ❗ Handle missing / bad text
        if len(article) < 500:
            mask = df["PMID"].astype(str) == pmid
            df.loc[mask, "Summary"] = "Full text not available"
            df.loc[mask, "Rationale"] = "PDF text extraction failed or incomplete"
            continue

        payload = {
            "input_type": "text",
            "output_type": "chat",
            "tweaks": {
                "Prompt-QH9TX": {
                    "ifu_context": ifu_text,
                    "article_text": article
                }
            }
        }

        headers = {"Content-Type": "application/json"}
        if API_KEY:
            headers["x-api-key"] = API_KEY

        try:
            r = requests.post(
                API_URL,
                json=payload,
                headers=headers,
                timeout=180
            )
            r.raise_for_status()
        except Exception as e:
            print(f"[ERROR] LLM API failed for PMID={pmid}: {e}")
            continue

        raw = r.json()

        try:
            text_out = raw["outputs"][0]["outputs"][0]["results"]["message"]["text"]
        except Exception:
            print(f"[ERROR] Unexpected LLM response format for PMID={pmid}")
            continue

        parsed = safe_parse_json(text_out, pmid)

        if not parsed:
            mask = df["PMID"].astype(str) == pmid
            df.loc[mask, "Summary"] = "LLM response invalid"
            df.loc[mask, "Rationale"] = "Model did not return valid JSON"
            continue

        mask = df["PMID"].astype(str) == pmid
        df.loc[mask, "Summary"] = parsed.get("Summary", "")
        df.loc[mask, "Rationale"] = parsed.get("Rationale", "")

    df.to_excel(output_excel, index=False)
    print(f"[SUCCESS] Secondary screening completed → {output_excel}")
