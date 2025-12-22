import os
import json
import re
import requests
import pandas as pd
from PyPDF2 import PdfReader
from dotenv import load_dotenv

load_dotenv()

SECONDARY_API_URL = os.getenv(
    "SECONDARY_API_URL",
    "http://localhost:7860/api/v1/run/secondary-screening"
)
SECONDARY_API_KEY = os.getenv("SECONDARY_API_KEY")


# ---------------- HELPERS ----------------

def read_ifu_from_pdf(pdf_path: str) -> str:
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"IFU PDF not found: {pdf_path}")
    if os.path.getsize(pdf_path) < 1024:
        raise ValueError("Invalid IFU PDF")

    reader = PdfReader(pdf_path)
    return "\n".join(page.extract_text() or "" for page in reader.pages)


def clean_json_text(text: str) -> str:
    text = re.sub(r"^```json", "", text.strip(), flags=re.I | re.M)
    text = re.sub(r"```$", "", text.strip(), flags=re.M)
    return text.strip("` \n\t")


def extract_score(code: str) -> int:
    m = re.search(r"(\d+)", str(code))
    return int(m.group(1)) if m else 0


def detect_secondary_parameters(article_text: str, study_type: str):
    text = article_text.lower()
    t = "T1" if study_type.lower() in text else "T2"
    o = "O1" if re.search(r"(outcome|efficacy|safety|result)", text) else "O2"
    f = "F1" if re.search(r"(follow[- ]?up|months|weeks|days)", text) else "F2"
    s = "S1" if re.search(r"(p[- ]?value|statistical)", text) else "S2"
    c = "C1" if re.search(r"(clinical|benefit|improvement)", text) else "C2"
    return t, o, f, s, c


def call_langflow(ifu_text: str, article_text: str):
    headers = {"Content-Type": "application/json"}
    if SECONDARY_API_KEY:
        headers["x-api-key"] = SECONDARY_API_KEY

    payload = {
        "input_type": "text",
        "output_type": "chat",
        "input_value": "",
        "tweaks": {
            "Prompt-QH9TX": {
                "ifu_context": ifu_text,
                "article_text": article_text
            }
        }
    }

    try:
        r = requests.post(
            SECONDARY_API_URL,
            json=payload,
            headers=headers,
            timeout=180
        )
        r.raise_for_status()
    except requests.RequestException as e:
        raise RuntimeError(f"LangFlow request failed: {e}")

    try:
        return r.json()
    except json.JSONDecodeError:
        raise ValueError(f"LangFlow returned non-JSON response:\n{r.text[:500]}")


# ---------------- MAIN RUNNER ----------------

def run_secondary_screening(
    primary_excel_path: str,
    ifu_pdf_path: str,
    text_dir: str,
    output_dir: str
) -> str:

    os.makedirs(output_dir, exist_ok=True)

    # Load IFU
    ifu_text = read_ifu_from_pdf(ifu_pdf_path)

    # Load Excel
    df = pd.read_excel(primary_excel_path)
    df.columns = [str(c).strip() for c in df.columns]

    if "PMID" not in df.columns:
        raise ValueError("Primary Excel must contain 'PMID' column")

    # Normalize PMID
    df["PMID"] = (
        df["PMID"]
        .astype(str)
        .str.strip()
        .str.replace(r"\.0$", "", regex=True)
    )

    df["Summary"] = df.get("Summary", "").astype("object")

    # Column finder
    def find_col(startswith):
        return next((c for c in df.columns if c.lower().startswith(startswith)), None)

    device_col = find_col("appropriate device")
    app_col = find_col("appropriate device application")
    patient_col = find_col("appropriate patient group")
    report_col = find_col("acceptable report")
    score_col = find_col("suitability")
    t_col = find_col("data source type")
    o_col = find_col("outcome measures")
    f_col = find_col("follow-up")
    s_col = find_col("statistical significance")
    c_col = find_col("clinical significance")
    dc_col = find_col("data contribution")
    male_col = find_col("no. of males")
    female_col = find_col("no. of females")
    age_col = find_col("mean age")
    result_col = find_col("result") or "Result"

    # Create missing columns
    for col in [
        "Summary", "Study type", "Device", "Sample size / No. of patients",
        device_col, app_col, patient_col, report_col,
        score_col, t_col, o_col, f_col, s_col, c_col,
        dc_col, male_col, female_col, age_col,
        result_col, "Rationale"
    ]:
        if col and col not in df.columns:
            df[col] = ""

    # ---------------- PROCESS ----------------
    for idx, row in df.iterrows():
        pmid = row["PMID"]
        txt_path = os.path.join(text_dir, f"{pmid}.txt")

        if not os.path.exists(txt_path):
            df.at[idx, "Summary"] = "Full text not found"
            continue

        with open(txt_path, "r", encoding="utf-8") as f:
            article_text = f.read()

        try:
            result = call_langflow(ifu_text, article_text)

            if (
                not result
                or "outputs" not in result
                or not result["outputs"]
                or not result["outputs"][0].get("outputs")
            ):
                raise ValueError("Invalid LangFlow response structure")

            msg = (
                result["outputs"][0]["outputs"][0]
                .get("results", {})
                .get("message", {})
                .get("text", "")
                .strip()
            )

            if not msg:
                raise ValueError("Empty LangFlow response text")

            parsed = json.loads(clean_json_text(msg))

        except Exception as e:
            df.at[idx, "Summary"] = f"LangFlow error: {e}"
            continue

        ad = parsed.get("Appropriate Device", "")
        aa = parsed.get("Appropriate Device Application", "")
        ap = parsed.get("Appropriate Patient Group", "")
        ar = parsed.get("Acceptable Report/Data Collation", "")

        suitability = extract_score(ad) + extract_score(aa) + extract_score(ap) + extract_score(ar)
        t, o, f, s, c = detect_secondary_parameters(article_text, parsed.get("Study type", ""))
        dc_score = sum(map(extract_score, [t, o, f, s, c]))

        df.at[idx, "Summary"] = parsed.get("Summary", "")
        df.at[idx, "Study type"] = parsed.get("Study type", "")
        df.at[idx, "Device"] = parsed.get("Device", "")
        df.at[idx, "Sample size / No. of patients"] = parsed.get("Sample size / No. of patients", "")

        df.at[idx, device_col] = ad
        df.at[idx, app_col] = aa
        df.at[idx, patient_col] = ap
        df.at[idx, report_col] = ar
        df.at[idx, score_col] = suitability

        df.at[idx, t_col] = t
        df.at[idx, o_col] = o
        df.at[idx, f_col] = f
        df.at[idx, s_col] = s
        df.at[idx, c_col] = c
        df.at[idx, dc_col] = dc_score

        df.at[idx, male_col] = parsed.get("No. of males", "NA")
        df.at[idx, female_col] = parsed.get("No. of females", "NA")
        df.at[idx, age_col] = parsed.get("Mean age", "NA")
        df.at[idx, "Rationale"] = parsed.get("Rationale", "")

        df.at[idx, result_col] = (
            "include" if suitability <= 8 and dc_score <= 8 else "exclude"
        )

    output_path = os.path.join(output_dir, "secondary_results.xlsx")
    df.to_excel(output_path, index=False)

    return output_path
