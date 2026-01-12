from sqlalchemy.orm import Session
from db.models.literature_model import Literature
from db.models.primary_screening_model import PrimaryScreening
from primary.primary_runner import (
    call_langflow,
    read_ifu_from_pdf,
    clean_json_text,
    safe_parse_json,
)

import logging

# ------------------------------------------------------------------
# Logger setup
# ------------------------------------------------------------------
logger = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO)


def run_primary_screening_for_project(
    db: Session,
    project_id: int,
    ifu_pdf_path: str
):
    ifu_text = read_ifu_from_pdf(ifu_pdf_path)

    articles = (
        db.query(Literature)
        .filter(
            Literature.project_id == project_id,
            Literature.is_unique == True,
            Literature.primary_screening == None
        )
        .all()
    )

    screened = 0

    for art in articles:
        abstract = art.abstract or ""

        result = call_langflow(ifu_text, abstract)

        decision = "ERROR"
        exclusion = ""
        rationale = ""

        if "outputs" in result:
            try:
                msg = result["outputs"][0]["outputs"][0]["results"]["message"]
                text_out = msg.get("data", {}).get("text") or msg.get("text", "")

                # ---------------- LOG RAW OUTPUT ----------------
                logger.info(
                    "RAW LLM OUTPUT | project_id=%s | literature_id=%s | text=%s",
                    project_id,
                    art.id,
                    text_out
                )

                clean_text = clean_json_text(text_out)
                parsed = safe_parse_json(clean_text)

                # ---------------- LOG PARSED OUTPUT ----------------
                logger.info(
                    "PARSED LLM OUTPUT | project_id=%s | literature_id=%s | parsed=%s",
                    project_id,
                    art.id,
                    parsed
                )

                # Robust key handling
                decision = (
                    parsed.get("Decision") 
                    or parsed.get("decision") 
                    or ""
                )
                exclusion = (
                    parsed.get("ExcludedCriteria")
                    or parsed.get("excludedCriteria")
                    or parsed.get("excluded_criteria")
                    or ""
                )
                rationale = (
                    parsed.get("Rationale")
                    or parsed.get("rationale")
                    or ""
                )

                # Guard against silent empty outputs
                if not decision:
                    rationale = "LLM response parsed but 'Decision' missing"

            except Exception as e:
                logger.exception(
                    "PRIMARY SCREENING PARSE ERROR | project_id=%s | literature_id=%s",
                    project_id,
                    art.id
                )
                rationale = f"Parse error: {e}"

        ps = PrimaryScreening(
            project_id=project_id,
            literature_id=art.id,
            decision=decision,
            exclusion_criteria=exclusion,
            rationale=rationale
        )

        db.add(ps)
        screened += 1

    db.commit()
    return screened
