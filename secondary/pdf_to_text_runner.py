import os
import fitz  # PyMuPDF


def run_pdf_to_text(pdf_dir: str, text_dir: str):
    """
    Convert all PDFs from pdf_dir to TXT files in text_dir
    """

    os.makedirs(text_dir, exist_ok=True)

    pdf_files = [
        f for f in os.listdir(pdf_dir)
        if f.lower().endswith(".pdf")
    ]

    if not pdf_files:
        return {
            "status": "no-pdfs",
            "message": "No PDF files found"
        }

    results = []

    for pdf_file in pdf_files:
        pdf_path = os.path.join(pdf_dir, pdf_file)
        txt_name = os.path.splitext(pdf_file)[0] + ".txt"
        txt_path = os.path.join(text_dir, txt_name)

        try:
            with fitz.open(pdf_path) as doc:
                text_content = []
                for page in doc:
                    text_content.append(page.get_text("text"))

            with open(txt_path, "w", encoding="utf-8") as f:
                f.write("\n\n".join(text_content))

            results.append({
                "pdf": pdf_file,
                "text": txt_name,
                "status": "converted"
            })

        except Exception as e:
            results.append({
                "pdf": pdf_file,
                "status": "failed",
                "error": str(e)
            })

    return {
        "status": "completed",
        "converted": len([r for r in results if r["status"] == "converted"]),
        "details": results
    }
