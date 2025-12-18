import os
import time
import pandas as pd
from selenium import webdriver
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.chrome.options import Options
from webdriver_manager.chrome import ChromeDriverManager

def download_pdfs(excel_path: str, pdf_dir: str):
    os.makedirs(pdf_dir, exist_ok=True)

    df = pd.read_excel(excel_path)
    if "PDF_Link" not in df.columns:
        raise ValueError("PDF_Link column missing")

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

    for _, row in df.iterrows():
        pmid = str(row.get("PMID", "")).strip()
        url = str(row.get("PDF_Link", "")).strip()

        if not url.startswith("http"):
            continue

        driver.get(url)
        time.sleep(5)

        files = [f for f in os.listdir(pdf_dir) if f.endswith(".pdf")]
        if files:
            latest = max(
                [os.path.join(pdf_dir, f) for f in files],
                key=os.path.getctime
            )
            os.rename(latest, os.path.join(pdf_dir, f"{pmid}.pdf"))

    driver.quit()
