import os
import requests
import pandas as pd
import json
import re
from PyPDF2 import PdfReader
from dotenv import load_dotenv
import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List
import time

load_dotenv()
API_URL = os.getenv("PRIMARY_API_URL", "http://localhost:7860/api/v1/run/primaryscreen-1-1-1")
API_KEY = os.getenv("PRIMARY_API_KEY")

logger = logging.getLogger(__name__)

# Configuration
MAX_WORKERS = 5  # Number of parallel requests
REQUEST_TIMEOUT = 30  # Timeout per request in seconds


def read_ifu_from_pdf(pdf_path: str) -> str:
    """Read and extract text from IFU PDF"""
    if not os.path.exists(pdf_path):
        raise FileNotFoundError(f"IFU PDF not found: {pdf_path}")
    
    logger.info(f"Reading IFU from: {pdf_path}")
    reader = PdfReader(pdf_path)
    text = [page.extract_text() or "" for page in reader.pages]
    ifu_text = "\n".join(text).strip()
    logger.info(f"Extracted {len(ifu_text)} characters from {len(reader.pages)} pages")
    return ifu_text


def clean_json_text(text: str) -> str:
    """Clean JSON response text"""
    text = re.sub(r"^```json", "", text.strip(), flags=re.IGNORECASE | re.MULTILINE)
    text = re.sub(r"^```", "", text.strip(), flags=re.MULTILINE)
    return text.strip("` \n\t")


def call_langflow(ifu: str, abstract: str, timeout: int = REQUEST_TIMEOUT) -> Dict:
    """
    Call Langflow API with timeout
    
    Args:
        ifu: IFU text
        abstract: Article abstract
        timeout: Request timeout in seconds
        
    Returns:
        Dict with Decision, Rationale, Category, ExcludedCriteria
    """
    headers = {"Content-Type": "application/json", "x-api-key": API_KEY}
    payload = {
        "output_type": "chat",
        "input_type": "text",
        "input_value": abstract,
        "tweaks": {"Prompt-QH9TX": {"ifu_text": ifu, "abstract_text": abstract}},
    }
    
    try:
        response = requests.post(
            API_URL, 
            json=payload, 
            headers=headers, 
            timeout=timeout
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.Timeout:
        logger.error(f"Request timeout after {timeout}s")
        return {"Decision": "ERROR", "Rationale": f"Request timeout after {timeout}s"}
    except requests.exceptions.RequestException as e:
        logger.error(f"Request error: {str(e)}")
        return {"Decision": "ERROR", "Rationale": f"Request error: {str(e)}"}
    except Exception as e:
        logger.error(f"Unexpected error: {str(e)}")
        return {"Decision": "ERROR", "Rationale": str(e)}


def process_single_article(row_data: tuple, ifu_text: str) -> Dict:
    """
    Process a single article
    
    Args:
        row_data: Tuple of (index, row_dict)
        ifu_text: IFU text content
        
    Returns:
        Dict with screening results
    """
    idx, row = row_data
    abstract = str(row.get("Abstract", ""))
    pmid = row.get("PMID", "")
    
    logger.info(f"Processing article {idx + 1}: PMID {pmid}")
    
    # Call API
    result = call_langflow(ifu_text, abstract)
    
    # Parse response
    if "outputs" in result:
        try:
            msg = result["outputs"][0]["outputs"][0]["results"]["message"]
            if "data" in msg and "text" in msg["data"]:
                text_out = msg["data"]["text"]
            elif "text" in msg:
                text_out = msg["text"]
            else:
                raise ValueError(f"No 'text' field found in message: {msg}")
            
            clean_text = clean_json_text(text_out)
            result = json.loads(clean_text)
            logger.info(f"✓ Article {idx + 1} processed: {result.get('Decision', 'UNKNOWN')}")
        except Exception as e:
            logger.error(f"✗ Parse error for article {idx + 1}: {str(e)}")
            result = {
                "Decision": "ERROR",
                "Category": "NA",
                "ExcludedCriteria": "NA",
                "Rationale": f"Parse error: {e}",
            }
    
    # Build record
    record = {
        "PMID": pmid,
        "Abstract": abstract,
        "Decision": result.get("Decision", result.get("decision", "ERROR")),
        "Category": result.get("Category", result.get("category", "NA")),
        "ExcludedCriteria": (
            ",".join(result.get("ExcludedCriteria", result.get("excludedCriteria", [])))
            if isinstance(result.get("ExcludedCriteria", result.get("excludedCriteria", "")), list)
            else result.get("ExcludedCriteria", result.get("excludedCriteria", "NA"))
        ),
        "Rationale": result.get("Rationale", result.get("rationale", "NA")),
    }
    
    return record


def run_primary_screening(
    input_excel_path: str, 
    ifu_pdf_path: str, 
    output_folder: str, 
    sheet_name: str = "Master",
    max_workers: int = MAX_WORKERS
) -> str:
    """
    Run primary screening with parallel processing
    
    Args:
        input_excel_path: Path to All-Merged.xlsx
        ifu_pdf_path: Path to IFU.pdf
        output_folder: Folder to save results (database/PRJ-XXX/primary)
        sheet_name: Excel sheet name to read (default: "Master")
        max_workers: Number of parallel workers (default: 5)
        
    Returns:
        Path to output Excel file
    """
    logger.info("="*60)
    logger.info("STARTING PRIMARY SCREENING")
    logger.info("="*60)
    
    start_time = time.time()
    
    # Create output folder
    os.makedirs(output_folder, exist_ok=True)
    logger.info(f"Output folder: {output_folder}")
    
    # Read IFU
    logger.info("Reading IFU PDF...")
    ifu_text = read_ifu_from_pdf(ifu_pdf_path)
    
    # Read Excel
    logger.info(f"Reading Excel file: {input_excel_path}")
    try:
        df = pd.read_excel(input_excel_path, sheet_name=sheet_name)
        logger.info(f"✓ Loaded {len(df)} articles from Excel")
    except Exception as e:
        logger.error(f"✗ Failed to read Excel: {str(e)}")
        # Try default sheet
        logger.info("Trying to read first sheet...")
        df = pd.read_excel(input_excel_path)
        logger.info(f"✓ Loaded {len(df)} articles from first sheet")
    
    if "Abstract" not in df.columns:
        raise ValueError(f"Excel must contain an 'Abstract' column. Found columns: {list(df.columns)}")
    
    # Prepare data for parallel processing
    logger.info(f"Starting parallel processing with {max_workers} workers...")
    row_data = list(df.iterrows())
    total_articles = len(row_data)
    
    results = []
    completed = 0
    
    # Process in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        # Submit all tasks
        future_to_idx = {
            executor.submit(process_single_article, (idx, row), ifu_text): idx 
            for idx, row in row_data
        }
        
        # Collect results as they complete
        for future in as_completed(future_to_idx):
            completed += 1
            progress = (completed / total_articles) * 100
            
            try:
                result = future.result()
                results.append(result)
                logger.info(f"Progress: {completed}/{total_articles} ({progress:.1f}%)")
            except Exception as e:
                idx = future_to_idx[future]
                logger.error(f"Error processing article {idx}: {str(e)}")
                # Add error record
                results.append({
                    "PMID": df.iloc[idx].get("PMID", ""),
                    "Abstract": str(df.iloc[idx].get("Abstract", "")),
                    "Decision": "ERROR",
                    "Category": "NA",
                    "ExcludedCriteria": "NA",
                    "Rationale": f"Processing error: {str(e)}"
                })
    
    # Sort results by original order (by PMID)
    results_df = pd.DataFrame(results)
    
    # Save to Excel
    output_excel_path = os.path.join(output_folder, "screening_results.xlsx")
    logger.info(f"Saving results to: {output_excel_path}")
    results_df.to_excel(output_excel_path, index=False)
    
    # Summary
    elapsed_time = time.time() - start_time
    logger.info("="*60)
    logger.info("PRIMARY SCREENING COMPLETED")
    logger.info(f"Total articles: {total_articles}")
    logger.info(f"Time taken: {elapsed_time:.1f} seconds")
    logger.info(f"Average time per article: {elapsed_time/total_articles:.2f}s")
    logger.info(f"Output saved to: {output_excel_path}")
    logger.info("="*60)
    
    return output_excel_path