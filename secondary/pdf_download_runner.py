import os
import time
from pathlib import Path
from Bio import Entrez
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager
from sqlalchemy.orm import Session

from db.models.literature_model import Literature
from db.models.primary_screening_model import PrimaryScreening
from db.models.pdf_download_status_model import PdfDownloadStatus

from secondary.pdf_to_text_runner import run_pdf_to_text


Entrez.email = "your_email@example.com"  # Replace with your email


def get_system_downloads_dir() -> str:
    """
    Returns the system Downloads directory for the current user
    Works on Windows, macOS, Linux
    """
    downloads = Path.home() / "Downloads"
    downloads.mkdir(exist_ok=True)
    return str(downloads)


def run_pdf_download(db: Session, project_id: int):
    """
    Download PDFs for:
      - source = PubMed
      - primary_screening.decision = INCLUDE

    PDFs are saved directly in the system Downloads folder:
    Downloads/CEP-CER_Project_<project_id>/

    After download → PDFs are converted to text automatically
    """

    # ------------------------
    # 1️ Create project folder
    # ------------------------
    base_dir = get_system_downloads_dir()
    project_folder = os.path.join(base_dir, f"CEP-CER_Project_{project_id}")
    os.makedirs(project_folder, exist_ok=True)

    # ------------------------
    # 2️ Ensure PdfDownloadStatus rows exist
    # ------------------------
    all_literature = (
        db.query(Literature)
        .filter(Literature.project_id == project_id)
        .all()
    )

    for lit in all_literature:
        exists = (
            db.query(PdfDownloadStatus)
            .filter_by(project_id=project_id, literature_id=lit.id)
            .first()
        )
        if not exists:
            db.add(
                PdfDownloadStatus(
                    project_id=project_id,
                    literature_id=lit.id,
                    status="pending"
                )
            )
    db.commit()

    # ------------------------
    # 3️ Fetch PubMed + INCLUDED
    # ------------------------
    pubmed_articles = (
        db.query(Literature, PrimaryScreening)
        .join(
            PrimaryScreening,
            Literature.id == PrimaryScreening.literature_id
        )
        .filter(
            Literature.project_id == project_id,
            Literature.source.ilike("pubmed"),
            PrimaryScreening.decision.ilike("include")
        )
        .all()
    )

    if not pubmed_articles:
        return {
            "status": "no_articles",
            "message": "No PubMed INCLUDE articles found"
        }

    # ------------------------
    # 4️ Selenium setup
    # ------------------------
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")

    prefs = {
        "download.default_directory": project_folder,
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )

    # ------------------------
    # 5️ Download PDFs
    # ------------------------
    for literature, _ in pubmed_articles:
        pdf_status = (
            db.query(PdfDownloadStatus)
            .filter_by(
                project_id=project_id,
                literature_id=literature.id
            )
            .first()
        )

        if pdf_status.status == "downloaded":
            continue

        # ---- Fetch PMCID ----
        try:
            handle = Entrez.elink(
                dbfrom="pubmed",
                db="pmc",
                id=str(literature.article_id)
            )
            record = Entrez.read(handle)
            handle.close()

            if not record or not record[0].get("LinkSetDb"):
                pdf_status.status = "not_found"
                db.commit()
                continue

            pmcid = f"PMC{record[0]['LinkSetDb'][0]['Link'][0]['Id']}"
            pdf_url = f"https://www.ncbi.nlm.nih.gov/pmc/articles/{pmcid}/pdf/"

            pdf_status.pmcid = pmcid
            pdf_status.pdf_url = pdf_url

        except Exception as e:
            pdf_status.status = "failed"
            pdf_status.error_message = f"PMCID fetch error: {e}"
            db.commit()
            continue

        # ---- Download PDF ----
        try:
            driver.get(pdf_url)
            time.sleep(5)

            pdf_files = [
                f for f in os.listdir(project_folder)
                if f.lower().endswith(".pdf")
            ]

            if not pdf_files:
                pdf_status.status = "not_downloaded"
                db.commit()
                continue

            latest_pdf = max(
                [os.path.join(project_folder, f) for f in pdf_files],
                key=os.path.getctime
            )

            final_path = os.path.join(
                project_folder,
                f"{literature.article_id}.pdf"
            )

            os.replace(latest_pdf, final_path)

            pdf_status.file_path = final_path
            pdf_status.status = "downloaded"
            pdf_status.error_message = None
            db.commit()

        except Exception as e:
            pdf_status.status = "failed"
            pdf_status.error_message = f"Selenium error: {e}"
            db.commit()

    driver.quit()

    # ------------------------
    # 6️ PDF → TEXT conversion
    # ------------------------
    text_dir = os.path.join(project_folder, "text")

    text_result = run_pdf_to_text(
        pdf_dir=project_folder,
        text_dir=text_dir
    )

    return {
        "status": "completed",
        "pdf_dir": project_folder,
        "text_dir": text_dir,
        "text_conversion": text_result
    }
