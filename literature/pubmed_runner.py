import os
import math
import time
import requests
import pandas as pd
import xml.etree.ElementTree as ET
from datetime import datetime

from services.literature_savedb import save_merged_to_db

# ---------------- CONFIG ----------------
BASE_URL = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils/"
TOOL = "pubmed_automation"
EMAIL = os.getenv("NCBI_EMAIL", "sales@iziel.com")
API_KEY = os.getenv("NCBI_API_KEY")

DEFAULT_SLEEP = 0.34 if not API_KEY else 0.12
MAX_RETRIES = 5
BATCH_SIZE = 200

session = requests.Session()

# ---------------- HELPERS ----------------
def _common_params():
    p = {"tool": TOOL, "email": EMAIL}
    if API_KEY:
        p["api_key"] = API_KEY
    return p

def safe_request(func, *args, **kwargs):
    retries = 0
    while True:
        try:
            return func(*args, **kwargs)
        except requests.exceptions.HTTPError as e:
            if e.response.status_code == 429 and retries < MAX_RETRIES:
                wait = (2 ** retries) * DEFAULT_SLEEP
                print(f"429 retry after {wait:.1f}s")
                time.sleep(wait)
                retries += 1
            else:
                raise

def sanitize(text: str) -> str:
    if not text:
        return ""
    return (
        text.replace("\x00", "")
            .replace("“", '"').replace("”", '"')
            .replace("‘", "'").replace("’", "'")
            .replace("\u00A0", " ")
            .replace("\u2013", "-").replace("\u2014", "-")
            .replace("\n", " ").replace("\r", " ")
            .strip()
    )

def build_query(keyword: str, filters_csv: str,
                APPLY_ABSTRACT=True, APPLY_FREE=False, APPLY_FULL=False):

    keyword = sanitize(keyword)
    filters_csv = sanitize(filters_csv)

    parts = [f"({keyword})", "english[lang]", "humans[mh]"]

    availability = []
    if APPLY_ABSTRACT:
        availability.append("hasabstract[text]")
    if APPLY_FREE:
        availability.append("free full text[sb]")
    if APPLY_FULL:
        availability.append("full text[sb]")
    if availability:
        parts.append("(" + " OR ".join(availability) + ")")

    # Apply publication-type filters from Excel
    if filters_csv and filters_csv.lower() != "nan":
        types = [t.strip() for t in filters_csv.split(",") if t.strip()]
        if types:
            parts.append(
                "(" + " OR ".join([f'"{t}"[Publication Type]' for t in types]) + ")"
            )

    return " AND ".join(parts)

def esearch_with_history(term: str, mindate=None, maxdate=None):
    time.sleep(DEFAULT_SLEEP)
    params = {
        "db": "pubmed",
        "term": term,
        "retmode": "json",
        "usehistory": "y",
        "datetype": "pdat",
        "mindate": mindate,
        "maxdate": maxdate
    }
    params.update(_common_params())
    r = safe_request(session.get, BASE_URL + "esearch.fcgi", params=params, timeout=60)
    r.raise_for_status()
    res = r.json()["esearchresult"]
    return int(res["count"]), res["querykey"], res["webenv"]

def efetch_batch(qk: str, we: str, retstart: int, retmax: int = BATCH_SIZE):
    params = {
        "db": "pubmed",
        "query_key": qk,
        "webenv": we,
        "retstart": retstart,
        "retmax": retmax,
        "retmode": "xml",
    }
    params.update(_common_params())
    r = safe_request(session.get, BASE_URL + "efetch.fcgi", params=params, timeout=120)
    r.raise_for_status()
    return r.text

def safe_text(el):
    return sanitize(el.text) if el is not None and el.text else ""

def xml_to_rows(xml_text: str):
    root = ET.fromstring(xml_text)
    rows = []

    for art in root.findall(".//PubmedArticle"):
        pmid = safe_text(art.find(".//PMID"))
        authors = ", ".join([
            f"{safe_text(a.find('LastName'))} {safe_text(a.find('Initials'))}".strip()
            for a in art.findall(".//AuthorList/Author")
        ])

        rows.append({
            "article_id": pmid,
            "title": safe_text(art.find(".//ArticleTitle")),
            "abstract": " ".join(
                safe_text(a) for a in art.findall(".//AbstractText")
            ),
            "journal": safe_text(art.find(".//Journal/Title")),
            "publication_year": safe_text(
                art.find(".//Journal/JournalIssue/PubDate/Year")
            ),
            "author": authors,
            "publication_type": ", ".join(
                safe_text(pt) for pt in art.findall(".//PublicationType")
            ),
            "doi": safe_text(art.find(".//ArticleId[@IdType='doi']")),
            "article_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else "",
            "source": "PubMed",
            "is_unique": True
        })

    return rows

# ---------------- MAIN PIPELINE ----------------
def run_pubmed_pipeline(
    project_id: int,
    db,
    keywords: list,
    apply_abstract=True,
    apply_free=False,
    apply_full=False,
    project_start_date="2025-01-01",
    project_end_date="2025-12-31"
):
    """
    Runtime keyword-based literature screening
    - Keywords NOT stored in DB
    - Uses project start/end dates ONLY
    - Excel used ONLY for filters
    """

    print(f"Found {len(keywords)} keywords for project {project_id}")

    mindate = datetime.strptime(project_start_date, "%Y-%m-%d").strftime("%Y/%m/%d")
    maxdate = datetime.strptime(project_end_date, "%Y-%m-%d").strftime("%Y/%m/%d")

    all_records = []

    for kw in keywords:
        term = build_query(
            kw.get("keyword", ""),
            kw.get("filters", ""),
            APPLY_ABSTRACT=apply_abstract,
            APPLY_FREE=apply_free,
            APPLY_FULL=apply_full
        )

        print(f"\nRunning PubMed for: {kw.get('keyword')}")
        print(f"Date Range: {mindate} → {maxdate}")

        count, qk, we = esearch_with_history(term, mindate, maxdate)
        print(f"PubMed results: {count}")

        for i in range(math.ceil(count / BATCH_SIZE)):
            time.sleep(DEFAULT_SLEEP)
            xml = efetch_batch(qk, we, i * BATCH_SIZE)
            rows = xml_to_rows(xml)

            for r in rows:
                r["project_id"] = project_id
                r["keyword_id"] = int(
                    str(kw.get("keyword_no", 0)).replace("#", "")
                )

            all_records.extend(rows)

    if not all_records:
        print("No literature found.")
        return 0

    df = pd.DataFrame(all_records)

    # Convert numerics safely
    df["publication_year"] = pd.to_numeric(df["publication_year"], errors="coerce")
    df["project_id"] = project_id
    df["keyword_id"] = pd.to_numeric(df["keyword_id"], errors="coerce").fillna(0).astype(int)

    return save_merged_to_db(df=df, db=db, project_id=project_id)
