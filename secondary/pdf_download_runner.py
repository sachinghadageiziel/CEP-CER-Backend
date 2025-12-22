import os
import time
import pandas as pd
from Bio import Entrez

from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager


# ==============================
# CONFIG
# ==============================
Entrez.email = "your_email@example.com"


# ==============================
# MAIN RUNNER
# ==============================
def run_pdf_download(excel_path: str, pdf_dir: str, output_dir: str):
    """
    1. Enrich Excel with PMCID + PDF links
    2. Download PDFs using Selenium
    3. Save final Excel with Status
    """

    os.makedirs(pdf_dir, exist_ok=True)
    os.makedirs(output_dir, exist_ok=True)

    df = pd.read_excel(excel_path)

    if "PMID" not in df.columns:
        raise ValueError("Excel must contain PMID column")

    # Ensure required columns
    for col in ["PMCID", "PDF_Link", "Status"]:
        if col not in df.columns:
            df[col] = ""

    # ==============================
    # STEP 1: FETCH PMCID + PDF LINKS
    # ==============================
    for i, row in df.iterrows():
        pmid = str(row["PMID"]).strip()

        if str(row["PMCID"]).startswith("PMC"):
            continue

        try:
            handle = Entrez.elink(dbfrom="pubmed", db="pmc", id=pmid)
            record = Entrez.read(handle)
            handle.close()

            if record and record[0].get("LinkSetDb"):
                pmcid = record[0]["LinkSetDb"][0]["Link"][0]["Id"]
                df.at[i, "PMCID"] = f"PMC{pmcid}"
                df.at[i, "PDF_Link"] = (
                    f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid}/pdf/"
                )
            else:
                df.at[i, "Status"] = "No-PMCID"

        except Exception:
            df.at[i, "Status"] = "PMCID-Error"

        time.sleep(0.5)

    # ==============================
    # STEP 2: SETUP SELENIUM
    # ==============================
    chrome_options = Options()
    chrome_options.add_argument("--headless=new")

    prefs = {
        "download.default_directory": os.path.abspath(pdf_dir),
        "download.prompt_for_download": False,
        "plugins.always_open_pdf_externally": True,
    }
    chrome_options.add_experimental_option("prefs", prefs)

    driver = webdriver.Chrome(
        service=Service(ChromeDriverManager().install()),
        options=chrome_options
    )

    # ==============================
    # STEP 3: DOWNLOAD PDFs
    # ==============================
    for i, row in df.iterrows():
        pmid = str(row["PMID"]).strip()
        url = str(row["PDF_Link"]).strip()

        if not url.startswith("http"):
            continue

        try:
            driver.get(url)
            time.sleep(6)

            pdf_files = [
                f for f in os.listdir(pdf_dir)
                if f.lower().endswith(".pdf")
            ]

            if not pdf_files:
                df.at[i, "Status"] = "Not-Downloaded"
                continue

            latest_pdf = max(
                [os.path.join(pdf_dir, f) for f in pdf_files],
                key=os.path.getctime
            )

            final_path = os.path.join(pdf_dir, f"{pmid}.pdf")
            os.replace(latest_pdf, final_path)

            df.at[i, "Status"] = "Downloaded"

        except Exception:
            df.at[i, "Status"] = "Download-Failed"

    driver.quit()

    # ==============================
    # STEP 4: SAVE FINAL EXCEL
    # ==============================
    output_excel = os.path.join(output_dir, "pdf_download_status.xlsx")
    df.to_excel(output_excel, index=False)

    return output_excel
