import pandas as pd
from Bio import Entrez
import time

Entrez.email = "your_email@example.com"

def enrich_with_pmcid(excel_path: str):
    df = pd.read_excel(excel_path)

    if "PMID" not in df.columns:
        raise ValueError("Excel must contain PMID column")

    if "PMCID" not in df.columns:
        df["PMCID"] = ""
    if "PDF_Link" not in df.columns:
        df["PDF_Link"] = ""

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
                df.at[i, "PDF_Link"] = f"https://pmc.ncbi.nlm.nih.gov/articles/PMC{pmcid}/pdf/"
        except Exception as e:
            print(f"[PMID {pmid}] Error: {e}")

        time.sleep(0.5)

    df.to_excel(excel_path, index=False)
