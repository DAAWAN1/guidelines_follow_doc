import fitz  # PyMuPDF
import pdfplumber
import io

def extract_text_and_images(uploaded_file):
    pdf_bytes = uploaded_file.read()
    image_count = 0
    text = ""

    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        for page in doc:
            text += page.get_text()
            image_count += len(page.get_images(full=True))
        doc.close()
        if text.strip():
            return text, image_count
    except Exception:
        pass

    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        return text, 0
    except Exception:
        return "", 0