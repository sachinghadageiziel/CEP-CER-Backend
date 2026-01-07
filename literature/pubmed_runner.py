import os
import math
import time
import requests
import pandas as pd
import xml.etree.ElementTree as ET

from db.models.literature_keywords_model import LiteratureKeyword
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
    """Sanitize keyword text for PubMed search."""
    if not text:
        return ""
    text = text.replace("“", '"').replace("”", '"')
    text = text.replace("‘", "'").replace("’", "'")
    text = text.replace("\u00A0", " ")  # non-breaking space
    text = text.replace("\u2013", "-").replace("\u2014", "-")
    text = text.replace("\n", " ").replace("\r", " ")
    return " ".join(text.split())  # collapse multiple spaces

def build_query(keyword: str, filters_csv: str,
                APPLY_ABSTRACT=True, APPLY_FREE=False, APPLY_FULL=False):

    keyword = sanitize(keyword)
    filters_csv = sanitize(filters_csv)

    parts = [f"({keyword})", "english[lang]", "humans[mh]"]

    avail = []
    if APPLY_ABSTRACT:
        avail.append("hasabstract[text]")
    if APPLY_FREE:
        avail.append("free full text[sb]")
    if APPLY_FULL:
        avail.append("full text[sb]")
    if avail:
        parts.append("(" + " OR ".join(avail) + ")")

    # ✅ Only add Publication Type filter if filters_csv is non-empty and not 'nan'
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
    }
    if mindate and maxdate:
        params.update({
            "datetype": "pdat",
            "mindate": mindate.replace("-", "/"),
            "maxdate": maxdate.replace("-", "/")
        })
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
    return (el.text or "").strip() if el is not None else ""

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
            "pmid": pmid,
            "title": safe_text(art.find(".//ArticleTitle")),
            "journal": safe_text(art.find(".//Journal/Title")),
            "pub_date": safe_text(art.find(".//Journal/JournalIssue/PubDate/Year")),
            "authors": authors,
            "abstract": "\n".join(safe_text(a) for a in art.findall(".//AbstractText")),
            "pubmed_url": f"https://pubmed.ncbi.nlm.nih.gov/{pmid}/" if pmid else ""
        })
    return rows

# ---------------- MAIN PIPELINE ----------------
def run_pubmed_pipeline(project_id: str, db,
                        apply_abstract=True, apply_free=False, apply_full=False,
                        from_date=None, to_date=None):
    """
    DB-based literature screening
    - Reads keywords from DB
    - Sanitizes keywords to fix encoding issues
    - Runs PubMed searches
    - Saves ALL rows (duplicates allowed)
    """

    keywords = db.query(LiteratureKeyword).filter(
        LiteratureKeyword.project_id == project_id,
        LiteratureKeyword.keyword_no.like("#%")
    ).all()

    print(f"Found {len(keywords)} keywords for project {project_id}")

    all_records = []

    for kw in keywords:
        clean_keyword = sanitize(kw.keyword)
        clean_filters = sanitize(kw.filters or "")

        term = build_query(
            clean_keyword,
            clean_filters,
            APPLY_ABSTRACT=apply_abstract,
            APPLY_FREE=apply_free,
            APPLY_FULL=apply_full
        )

        print(f"Running PubMed for keyword: {clean_keyword}")
        print(f"DEBUG TERM: {term}")

        count, qk, we = esearch_with_history(term, from_date, to_date)
        print(f"PubMed count = {count}")

        if count == 0:
            continue

        loops = math.ceil(count / BATCH_SIZE)

        for i in range(loops):
            time.sleep(DEFAULT_SLEEP)
            xml = efetch_batch(qk, we, i * BATCH_SIZE)
            rows = xml_to_rows(xml)

            for r in rows:
                r["keyword_no"] = kw.keyword_no

            all_records.extend(rows)

    print(f"Total records collected: {len(all_records)}")

    if not all_records:
        return 0

    df = pd.DataFrame(all_records)

    return save_merged_to_db(
        df=df,
        db=db,
        project_id=project_id
    )
