import os
import fitz  # PyMuPDF

def convert_pdf_to_text(pdf_dir: str, text_dir: str):
    os.makedirs(text_dir, exist_ok=True)

    for file in os.listdir(pdf_dir):
        if not file.lower().endswith(".pdf"):
            continue

        pdf_path = os.path.join(pdf_dir, file)
        txt_path = os.path.join(text_dir, file.replace(".pdf", ".txt"))

        with fitz.open(pdf_path) as doc:
            text = ""
            for page in doc:
                text += page.get_text()

        with open(txt_path, "w", encoding="utf-8") as f:
            f.write(text)
