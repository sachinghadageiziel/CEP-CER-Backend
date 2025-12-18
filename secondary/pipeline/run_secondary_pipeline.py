import os
from secondary.steps.step_01_fetch_pmcid import enrich_with_pmcid
from secondary.steps.step_02_download_pdf import download_pdfs
from secondary.steps.step_03_pdf_to_text import convert_pdf_to_text
from secondary.steps.step_04_secondary_llm import run_secondary_screening

def run_secondary_pipeline(project_id: str) -> str:
    base = os.path.join("database", project_id, "secondary")

    excel = os.path.join(base, "working.xlsx")
    ifu = os.path.join(base, "ifu.pdf")
    pdf_dir = os.path.join(base, "pdf")
    text_dir = os.path.join(base, "text")
    result = os.path.join(base, "result.xlsx")

    enrich_with_pmcid(excel)
    download_pdfs(excel, pdf_dir)
    convert_pdf_to_text(pdf_dir, text_dir)
    run_secondary_screening(excel, text_dir, ifu, result)

    return result
