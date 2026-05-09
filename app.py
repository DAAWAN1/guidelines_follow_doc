import streamlit as st
import fitz  # PyMuPDF
import os
import json
import pickle
import numpy as np
import re
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import pdfplumber
import io
from huggingface_hub import InferenceClient

# ------------------------------------------------------------------
# Environment & config
# ------------------------------------------------------------------
load_dotenv()
if os.getenv("HF_TOKEN"):
    os.environ["HF_TOKEN"] = os.getenv("HF_TOKEN")

st.set_page_config(page_title="GSK Document Intelligence", layout="wide")
st.title("📄 GSK Document Intelligence")
st.markdown(
    """
    Upload the **Guidelines PDF** first, then an **Article PDF** to check compliance.
    The app extracts text, creates embeddings (for future use), and now performs
    **deterministic rule‑based checks** on the article’s forensic description.
    """
)

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------
for key in [
    "guidelines_uploaded",
    "guidelines_text",
    "guidelines_chunks",
    "guidelines_embeddings",
    "article_uploaded",
    "article_text",
]:
    if key not in st.session_state:
        st.session_state[key] = None

# ------------------------------------------------------------------
# Original helper functions (unchanged)
# ------------------------------------------------------------------
def extract_text_from_pdf(uploaded_file) -> str:
    pdf_bytes = uploaded_file.read()
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return text
    except Exception:
        pass
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if text.strip():
            return text
    except Exception:
        pass
    return ""

def chunk_text(text: str, chunk_size_words=500, overlap_words=50) -> list:
    words = text.split()
    chunks = []
    start = 0
    while start < len(words):
        end = min(start + chunk_size_words, len(words))
        chunk_words = words[start:end]
        chunk_text = " ".join(chunk_words)
        chunks.append(
            {
                "chunk_id": len(chunks),
                "text": chunk_text,
                "word_count": len(chunk_words),
            }
        )
        start += chunk_size_words - overlap_words
        if start >= len(words):
            break
    return chunks

@st.cache_resource
def load_embedding_model():
    return SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")

def embed_chunks(chunks: list, model) -> tuple:
    embeddings = []
    token_counts = []
    for chunk in chunks:
        encoded = model.tokenize([chunk["text"]])
        token_count = len(encoded["input_ids"][0])
        token_counts.append(token_count)
        emb = model.encode(chunk["text"], convert_to_numpy=True)
        embeddings.append(emb)
    return embeddings, token_counts

def save_guidelines(chunks, embeddings, token_counts):
    chunks_data = []
    for i, chunk in enumerate(chunks):
        chunks_data.append(
            {
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "token_count": token_counts[i],
            }
        )
    with open("guidelines_chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks_data, f, indent=2)
    with open("guidelines_embeddings.pkl", "wb") as f:
        pickle.dump(embeddings, f)

def reset_state():
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    for fname in ["guidelines_chunks.json", "guidelines_embeddings.pkl"]:
        if os.path.exists(fname):
            os.remove(fname)

# ------------------------------------------------------------------
# New: deterministic rule checker
# ------------------------------------------------------------------

def check_article_compliance(article_text: str) -> list:
    """
    Run a set of rule‑based checks against the forensic article text.
    Returns a list of dicts: {rule, status, explanation}
    """
    rules = []

    # ----- Rule 1: Mandatory feedback callout -----
    target_phrase = (
        "Did this article meet your needs? "
        "Click Yes to let us know! If No, please share what's missing so we can improve the content."
    )
    if target_phrase in article_text:
        rules.append({
            "rule": "Feedback callout (QUESTION type)",
            "status": "✅ Followed",
            "explanation": "The mandatory feedback callout phrase is present."
        })
    else:
        rules.append({
            "rule": "Feedback callout (QUESTION type)",
            "status": "❌ Violated",
            "explanation": "The exact phrase is not found anywhere in the article."
        })

    # ----- Rule 2: Table header orange background + bold white text -----
    # Look for "orange background" and "bold white" in the table header description
    if re.search(r"orange\s*background.*bold\s*white", article_text, re.IGNORECASE):
        rules.append({
            "rule": "Table header row orange background & bold white text",
            "status": "✅ Followed",
            "explanation": "Table header described with orange background and white bold text."
        })
    elif re.search(r"grey tint|no colour background|dark\s*/\s*black\s*text", article_text, re.IGNORECASE):
        rules.append({
            "rule": "Table header row orange background & bold white text",
            "status": "❌ Violated",
            "explanation": "Table header has a grey tint and dark text instead of orange background with white text."
        })
    else:
        rules.append({
            "rule": "Table header row orange background & bold white text",
            "status": "⚠️ Undetermined",
            "explanation": "Could not conclusively verify the table header styling from the text."
        })

    # ----- Rule 3: Section headings must use Heading 2 style (orange/red) -----
    # The article describes its headings as "near‑black / very dark charcoal", which violates.
    if re.search(r"Section Headings.*?Colour:.*?(Near-black|dark charcoal|#1[aA]1[aA]1[aA]|#222222)", article_text):
        rules.append({
            "rule": "Section headings use official Heading 2 style (orange/red)",
            "status": "❌ Violated",
            "explanation": "Section headings are described as near‑black/dark charcoal, not orange/red."
        })
    elif re.search(r"orange/red|#F36633|GSK orange", article_text):
        rules.append({
            "rule": "Section headings use official Heading 2 style (orange/red)",
            "status": "✅ Followed",
            "explanation": "Headings are described using the GSK orange/red colour."
        })
    else:
        rules.append({
            "rule": "Section headings use official Heading 2 style (orange/red)",
            "status": "⚠️ Undetermined",
            "explanation": "Could not detect heading colour description."
        })

    # ----- Rule 4: Article Description section -----
    if re.search(r"Description.*?\n", article_text) and "This Knowledge Article" in article_text:
        rules.append({
            "rule": "Article contains a Description section",
            "status": "✅ Followed",
            "explanation": "A Description section starting with 'This Knowledge Article...' is present."
        })
    else:
        rules.append({
            "rule": "Article contains a Description section",
            "status": "❌ Violated",
            "explanation": "No Description block found; article should begin with a short summary."
        })

    # ----- Rule 5: Contacts for Further Help section -----
    if re.search(r"Contacts for Further Help|Contact for Further Help", article_text, re.IGNORECASE):
        rules.append({
            "rule": "Contacts for Further Help section",
            "status": "✅ Followed",
            "explanation": "A contacts section is present."
        })
    else:
        rules.append({
            "rule": "Contacts for Further Help section",
            "status": "❌ Violated",
            "explanation": "No contacts section found. Every article must include one."
        })

    # ----- Rule 6: Hyperlinks are blue & underlined -----
    if "blue" in article_text and "underline" in article_text:
        rules.append({
            "rule": "Hyperlinks appear blue and underlined",
            "status": "✅ Followed",
            "explanation": "The article explicitly states hyperlinks are blue with underline."
        })
    else:
        rules.append({
            "rule": "Hyperlinks appear blue and underlined",
            "status": "⚠️ Undetermined",
            "explanation": "Could not verify hyperlink colour/underline from text."
        })

    # ----- Rule 7: Copy Link button present -----
    if "Copy Link" in article_text:
        rules.append({
            "rule": "Copy Link button visible",
            "status": "✅ Followed",
            "explanation": "The Copy Link button is mentioned in the article."
        })
    else:
        rules.append({
            "rule": "Copy Link button visible",
            "status": "❌ Violated",
            "explanation": "No mention of a Copy Link button."
        })

    # ----- Rule 8: Table uses Paragraph style (not Heading) for cell text -----
    # Check if the article mentions "Paragraph" style for table text.
    if re.search(r"Paragraph.*style.*table|table.*Paragraph.*style", article_text, re.IGNORECASE):
        rules.append({
            "rule": "Table cell text uses Paragraph style",
            "status": "✅ Followed",
            "explanation": "Table cells are styled with Paragraph."
        })
    else:
        rules.append({
            "rule": "Table cell text uses Paragraph style",
            "status": "⚠️ Undetermined",
            "explanation": "Paragraph style usage not clearly described for tables."
        })

    # ----- Rule 9: Table has 3 columns -----
    if "3 columns" in article_text or "3-column" in article_text:
        rules.append({
            "rule": "Table has exactly 3 columns",
            "status": "✅ Followed",
            "explanation": "The article describes a 3‑column table."
        })
    else:
        rules.append({
            "rule": "Table has exactly 3 columns",
            "status": "❌ Violated",
            "explanation": "The table does not appear to have 3 columns."
        })

    # ----- Rule 10: Country label "Poland" is orange/red -----
    if re.search(r"(Poland).*?(orange|#E8490F|#F04E23)", article_text, re.IGNORECASE):
        rules.append({
            "rule": "Country label 'Poland' is coloured orange/red",
            "status": "✅ Followed",
            "explanation": "The label 'Poland' is correctly coloured orange/red."
        })
    else:
        rules.append({
            "rule": "Country label 'Poland' is coloured orange/red",
            "status": "❌ Violated",
            "explanation": "The label does not use the GSK brand orange."
        })

    return rules


@st.cache_resource
def load_inference_client():
    token = os.getenv("HF_TOKEN")
    if not token:
        st.error("HF_TOKEN not found. Set it in .env.")
        st.stop()
    return InferenceClient(token=token)


def generate_summary_from_results(results: list, client) -> str:
    """Generate a concise summary paragraph from the rule check results."""
    # Build a bullet list of findings
    findings = ""
    for r in results:
        findings += f"- {r['status']} {r['rule']}: {r['explanation']}\n"

    prompt = f"""You are a compliance analyst. Given the following rule‑check results for a GSK Knowledge Article, write a short, flowing paragraph (max 120 words) summarising the overall compliance, highlighting which major rules are followed and which are violated. Use plain English.

Results:
{findings}

Summary:"""
    try:
        completion = client.chat_completion(
            messages=[{"role": "user", "content": prompt}],
            model="katanemo/Arch-Router-1.5B",
            max_tokens=150,
            temperature=0.2,
        )
        return completion.choices[0].message["content"]
    except Exception as e:
        # Fallback: simple manual summary
        violated = [r for r in results if "Violated" in r["status"]]
        followed = [r for r in results if "Followed" in r["status"]]
        summary = f"The article follows {len(followed)} rules, but violates {len(violated)} rules. "
        if violated:
            summary += "Key violations: " + "; ".join([r["rule"] for r in violated]) + "."
        return summary


# ------------------------------------------------------------------
# Sidebar reset
# ------------------------------------------------------------------
st.sidebar.button("🔄 Reset Application", on_click=reset_state)

# ==================================================================
# SECTION 1: Upload Guidelines PDF (unchanged, only for embedding storage)
# ==================================================================
st.header("📘 Step 1: Upload Guidelines PDF")
guidelines_file = st.file_uploader(
    "Choose the GSK Knowledge Article Guidelines PDF",
    type=["pdf"],
    key="guidelines_uploader",
)

if guidelines_file is not None and guidelines_file != st.session_state.get("guidelines_uploaded"):
    st.session_state.guidelines_uploaded = guidelines_file
    st.session_state.guidelines_text = None
    st.session_state.guidelines_chunks = None
    st.session_state.guidelines_embeddings = None

    with st.spinner("Extracting guidelines text..."):
        text = extract_text_from_pdf(guidelines_file)
        if not text.strip():
            st.error("No text extracted from guidelines PDF.")
            st.stop()
        st.session_state.guidelines_text = text
        st.success("Guidelines text extracted.")

    with st.spinner("Chunking and embedding guidelines (for later use)..."):
        chunks = chunk_text(text)
        model = load_embedding_model()
        embeddings, token_counts = embed_chunks(chunks, model)
        st.session_state.guidelines_chunks = chunks
        st.session_state.guidelines_embeddings = embeddings
        save_guidelines(chunks, embeddings, token_counts)
        st.success(f"Guidelines stored ({len(chunks)} chunks).")

if st.session_state.guidelines_chunks is not None:
    st.markdown("✅ Guidelines are loaded and ready.")

st.markdown("---")

# ==================================================================
# SECTION 2: Upload Article PDF & Check Compliance
# ==================================================================
st.header("📄 Step 2: Upload Article PDF for Compliance Check")
article_file = st.file_uploader(
    "Choose the Knowledge Article PDF to verify",
    type=["pdf"],
    key="article_uploader",
    disabled=st.session_state.guidelines_chunks is None,
)

if article_file is not None and article_file != st.session_state.get("article_uploaded"):
    if st.session_state.guidelines_chunks is None:
        st.warning("Upload guidelines first.")
        st.stop()

    st.session_state.article_uploaded = article_file
    st.session_state.article_text = None

    with st.spinner("Extracting article text..."):
        text = extract_text_from_pdf(article_file)
        if not text.strip():
            st.error("No text extracted from article PDF.")
            st.stop()
        st.session_state.article_text = text
        st.success("Article text extracted.")

# If article text is available, run rule checks
if st.session_state.article_text is not None:
    st.markdown("---")
    st.subheader("🔍 Compliance Analysis")

    with st.spinner("Running deterministic rule checks..."):
        results = check_article_compliance(st.session_state.article_text)

    # Display results in a table
    st.write("### Detailed Rule‑by‑Rule Assessment")
    for i, r in enumerate(results):
        with st.expander(f"{r['status']} {r['rule']}"):
            st.write(r["explanation"])

    # Summary paragraph
    st.write("### 🧾 Overall Summary")
    client = load_inference_client()
    summary = generate_summary_from_results(results, client)
    st.success(summary)

    # Download report
    report_text = "\n\n".join(
        f"{r['status']} {r['rule']}\n{r['explanation']}" for r in results
    )
    st.download_button(
        "Download Full Report",
        data=report_text,
        file_name="compliance_report.txt",
        mime="text/plain",
    )

# ------------------------------------------------------------------
# Footer
# ------------------------------------------------------------------
st.markdown("---")
st.caption("Guidelines stored locally for future use.")