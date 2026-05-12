import fitz  # PyMuPDF
import pdfplumber
import io
from docx import Document


def extract_text_and_images(uploaded_file):
    """
    Extract text and image count from a PDF or DOCX file.
    Returns (text: str, image_count: int).
    """
    pdf_bytes = uploaded_file.read()
    extension = uploaded_file.name.rsplit(".", 1)[-1].lower() if "." in uploaded_file.name else "pdf"

    if extension == "pdf":
        # Use existing PDF extraction (PyMuPDF first, pdfplumber fallback)
        text = ""
        image_count = 0
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

    elif extension == "docx":
        # DOCX extraction using python-docx
        try:
            doc = Document(io.BytesIO(pdf_bytes))
            # Extract all paragraph text
            text = "\n".join(para.text for para in doc.paragraphs)

            # Count images (inline shapes) – works for most typical documents
            image_count = len(doc.inline_shapes)

            return text, image_count
        except Exception:
            return "", 0
    else:
        # Unsupported file type – should not happen because uploader restricts types
        return "", 0