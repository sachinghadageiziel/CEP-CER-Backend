import os
import json
import re
import requests
from io import BytesIO
from PyPDF2 import PdfReader
from dotenv import load_dotenv
from sqlalchemy.orm import Session

from db.models.project_model import Project
from db.models.primary_screening_model import PrimaryScreening
from db.models.secondary_screening_model import SecondaryScreening
from db.models.literature_model import Literature

load_dotenv()

SECONDARY_API_URL = os.getenv(
    "SECONDARY_API_URL",
    "http://localhost:7860/api/v1/run/secondary-screening"
)
SECONDARY_API_KEY = os.getenv("SECONDARY_API_KEY")


# -------------------------------------------------
# IFU FROM DB
# -------------------------------------------------
def read_ifu_from_bytes(pdf_bytes: bytes) -> str:
    reader = PdfReader(BytesIO(pdf_bytes))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


# -------------------------------------------------
# HELPERS
# -------------------------------------------------
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


def call_langflow(ifu_text: str, article_text: str) -> dict:
    headers = {"Content-Type": "application/json"}
    if SECONDARY_API_KEY:
        headers["x-api-key"] = SECONDARY_API_KEY

    payload = {
        "input_type": "text",
        "output_type": "chat",
        "input_value": "",
        "tweaks": {
            "Prompt-81K11": {
                "ifu_context": ifu_text,
                "article_text": article_text
            }
        }
    }

    r = requests.post(
        SECONDARY_API_URL,
        json=payload,
        headers=headers,
        timeout=180
    )
    r.raise_for_status()
    return r.json()


# -------------------------------------------------
# MAIN DB RUNNER
# -------------------------------------------------
def run_secondary_screening_db(
    db: Session,
    project_id: int
) -> int:
    """
    Secondary screening using FULL TEXT only.
    If PDF/TXT not available → record created with NA values.
    """

    # 1️ Project & IFU
    project = db.query(Project).filter(Project.id == project_id).first()
    if not project or not project.ifu_file_data:
        raise ValueError("IFU not found for project")

    ifu_text = read_ifu_from_bytes(project.ifu_file_data)

    # 2️ Included primary screenings
    primaries = (
        db.query(PrimaryScreening)
        .filter(
            PrimaryScreening.project_id == project_id,
            PrimaryScreening.decision == "INCLUDE"
        )
        .all()
    )

    if not primaries:
        return 0

    # TXT directory
    text_dir = os.path.join(
        os.path.expanduser("~"),
        "Downloads",
        f"CEP-CER_Project_{project_id}",
        "text"
    )

    processed = 0

    # 3️ Process each article
    for p in primaries:
        literature = (
            db.query(Literature)
            .filter(Literature.id == p.literature_id)
            .first()
        )

        if not literature:
            continue

        # Skip if already processed
        exists = (
            db.query(SecondaryScreening)
            .filter(
                SecondaryScreening.project_id == project_id,
                SecondaryScreening.literature_id == literature.id
            )
            .first()
        )
        if exists:
            continue

        txt_path = os.path.join(text_dir, f"{literature.article_id}.txt")

        # -------------------------------------------------
        #  CASE 1: PDF / TXT NOT AVAILABLE
        # -------------------------------------------------
        if not os.path.exists(txt_path):
            record = SecondaryScreening(
                project_id=project_id,
                literature_id=literature.id,
                summary="PDF not available",
                study_type="NA",
                device="NA",
                sample_size="NA",
                appropriate_device="NA",
                appropriate_device_application="NA",
                appropriate_patient_group="NA",
                acceptable_report="NA",
                suitability_score=0,
                data_contribution_score=0,
                data_source_type="NA",
                outcome_measures="NA",
                follow_up="NA",
                statistical_significance="NA",
                clinical_significance="NA",
                number_of_males=None,
                number_of_females=None,
                mean_age=None,
                result="EXCLUDE",
                rationale="Full-text PDF not available"
            )

            db.add(record)
            processed += 1
            continue

        # -------------------------------------------------
        #  CASE 2: FULL TEXT AVAILABLE
        # -------------------------------------------------
        with open(txt_path, "r", encoding="utf-8") as f:
            article_text = f.read().strip()

        if not article_text:
            article_text = ""

        try:
            response = call_langflow(ifu_text, article_text)

            msg = (
                response["outputs"][0]["outputs"][0]
                .get("results", {})
                .get("message", {})
                .get("text", "")
                .strip()
            )

            parsed = json.loads(clean_json_text(msg))

        except Exception as e:
            parsed = {
                "Summary": f"LangFlow error: {e}",
                "Rationale": str(e)
            }

        ad = parsed.get("Appropriate Device", "")
        aa = parsed.get("Appropriate Device Application", "")
        ap = parsed.get("Appropriate Patient Group", "")
        ar = parsed.get("Acceptable Report/Data Collation", "")

        suitability = (
            extract_score(ad)
            + extract_score(aa)
            + extract_score(ap)
            + extract_score(ar)
        )

        t, o, f, s, c = detect_secondary_parameters(
            article_text,
            parsed.get("Study type", "")
        )

        dc_score = sum(map(extract_score, [t, o, f, s, c]))

        result = "INCLUDE" if suitability <= 8 and dc_score <= 8 else "EXCLUDE"

        record = SecondaryScreening(
            project_id=project_id,
            literature_id=literature.id,
            summary=parsed.get("Summary"),
            study_type=parsed.get("Study type"),
            device=parsed.get("Device"),
            sample_size=parsed.get("Sample size / No. of patients"),
            appropriate_device=ad,
            appropriate_device_application=aa,
            appropriate_patient_group=ap,
            acceptable_report=ar,
            suitability_score=suitability,
            data_contribution_score=dc_score,
            data_source_type=t,
            outcome_measures=o,
            follow_up=f,
            statistical_significance=s,
            clinical_significance=c,
            number_of_males=parsed.get("No. of males"),
            number_of_females=parsed.get("No. of females"),
            mean_age=parsed.get("Mean age"),
            result=result,
            rationale=parsed.get("Rationale")
        )

        db.add(record)
        processed += 1

    db.commit()
    return processed
