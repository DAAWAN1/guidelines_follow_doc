import streamlit as st
import fitz  # PyMuPDF
import os
import json
import pickle
import numpy as np
from sentence_transformers import SentenceTransformer
from dotenv import load_dotenv
import pdfplumber
import io

# ------------------------------------------------------------------
# Load environment variables from .env file and set HF token
# ------------------------------------------------------------------
load_dotenv()
if os.getenv("HF_TOKEN"):
    os.environ["HF_TOKEN"] = os.getenv("HF_TOKEN")

# ------------------------------------------------------------------
# Page config
# ------------------------------------------------------------------
st.set_page_config(page_title="GSK Document Intelligence", layout="wide")
st.title("📄 GSK Document Intelligence")
st.markdown("Upload a PDF, extract text, vectorize, and save embeddings locally.")

# ------------------------------------------------------------------
# Session state initialisation
# ------------------------------------------------------------------
for key in ["uploaded_file", "extracted_text", "chunks", "embeddings"]:
    if key not in st.session_state:
        st.session_state[key] = None

# ------------------------------------------------------------------
# Helper functions
# ------------------------------------------------------------------

def extract_text_from_pdf(uploaded_file) -> str:
    pdf_bytes = uploaded_file.read()
    
    # 1. Try PyMuPDF
    try:
        doc = fitz.open(stream=pdf_bytes, filetype="pdf")
        text = "\n".join(page.get_text() for page in doc)
        doc.close()
        if text.strip():
            return text
    except Exception:
        pass

    # 2. Try pdfplumber
    try:
        with pdfplumber.open(io.BytesIO(pdf_bytes)) as pdf:
            text = "\n".join(page.extract_text() or "" for page in pdf.pages)
        if text.strip():
            return text
    except Exception:
        pass

    return ""

def chunk_text(text: str, chunk_size_words=500, overlap_words=50) -> list:
    """
    Split text into overlapping chunks of approximately `chunk_size_words` words.
    Returns a list of dictionaries with chunk id, text, and word count.
    """
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
    """Load the sentence-transformers model (cached)."""
    try:
        model = SentenceTransformer("sentence-transformers/all-MiniLM-L6-v2")
        return model
    except Exception as e:
        raise RuntimeError(f"Failed to load embedding model: {e}")


def embed_chunks(chunks: list, model) -> tuple:
    """
    Generate embeddings and token counts for each chunk.
    Returns (list of numpy arrays, list of token counts).
    """
    embeddings = []
    token_counts = []
    for chunk in chunks:
        # Token count using the model's tokenizer
        encoded = model.tokenize([chunk["text"]])
        token_count = len(encoded["input_ids"][0])
        token_counts.append(token_count)

        # Embedding
        emb = model.encode(chunk["text"], convert_to_numpy=True)
        embeddings.append(emb)

    return embeddings, token_counts


def save_chunks_and_embeddings(chunks, embeddings, token_counts):
    """Save chunks metadata and embedding vectors to local files."""
    # chunks.json: list of dicts with chunk_id, text, token_count
    chunks_data = []
    for i, chunk in enumerate(chunks):
        chunks_data.append(
            {
                "chunk_id": chunk["chunk_id"],
                "text": chunk["text"],
                "token_count": token_counts[i],
            }
        )
    with open("chunks.json", "w", encoding="utf-8") as f:
        json.dump(chunks_data, f, indent=2)

    # embeddings.pkl: list of numpy arrays
    with open("embeddings.pkl", "wb") as f:
        pickle.dump(embeddings, f)


def reset_state():
    """Clear all session state and reset the app."""
    for key in list(st.session_state.keys()):
        del st.session_state[key]
    # No explicit rerun needed - Streamlit will rerun automatically

# ------------------------------------------------------------------
# Sidebar: Reset button
# ------------------------------------------------------------------
st.sidebar.button("🔄 Reset Application", on_click=reset_state)

# ------------------------------------------------------------------
# File uploader
# ------------------------------------------------------------------
uploaded_file = st.file_uploader(
    "Choose a PDF file", type=["pdf"], key="pdf_uploader"
)

if uploaded_file is not None and uploaded_file != st.session_state.get("uploaded_file"):
    # New file uploaded – clear previous results and process
    st.session_state.uploaded_file = uploaded_file
    st.session_state.extracted_text = None
    st.session_state.chunks = None
    st.session_state.embeddings = None

    # 1. Extract text
    with st.spinner("Extracting text from PDF..."):
        try:
            text = extract_text_from_pdf(uploaded_file)
            if not text.strip():
                st.error("No text could be extracted from the PDF.")
                st.stop()
            st.session_state.extracted_text = text
            st.success("Text extracted successfully!")
        except Exception as e:
            st.error(f"Text extraction failed: {e}")
            st.stop()

    # 2. Chunking
    with st.spinner("Chunking text..."):
        chunks = chunk_text(text)
        if not chunks:
            st.error("Text chunking produced no chunks.")
            st.stop()
        st.session_state.chunks = chunks
        st.info(f"Created {len(chunks)} chunks (each ~500 words).")

    # 3. Vectorization
    with st.spinner("Loading embedding model and vectorizing..."):
        try:
            model = load_embedding_model()
            embeddings, token_counts = embed_chunks(chunks, model)
            st.session_state.embeddings = embeddings
            st.success(f"Embeddings generated for {len(chunks)} chunks.")

            # Save chunks and embeddings locally
            save_chunks_and_embeddings(chunks, embeddings, token_counts)
            st.success("Saved chunks.json and embeddings.pkl.")
        except Exception as e:
            st.error(f"Vectorization failed: {e}")
            st.stop()

# ------------------------------------------------------------------
# Display results if we have data
# ------------------------------------------------------------------
if st.session_state.uploaded_file is not None:
    st.markdown("---")
    st.subheader("📄 Uploaded File")
    st.write(f"**Name:** {st.session_state.uploaded_file.name}")

    st.markdown("---")
    st.subheader("🧩 Chunking & Embedding")
    if st.session_state.chunks:
        num_chunks = len(st.session_state.chunks)
        st.write(f"**Number of chunks:** {num_chunks}")
        if st.session_state.embeddings and len(st.session_state.embeddings) > 0:
            sample_emb = st.session_state.embeddings[0]
            st.write(f"**Sample embedding vector (first 10 values):** {sample_emb[:10]}")
            st.caption(f"(Full vector dimension: {len(sample_emb)})")
    else:
        st.info("No chunks available.")

# ------------------------------------------------------------------
# Footer: indicate local files saved
# ------------------------------------------------------------------
st.markdown("---")
st.caption(
    "All generated data (chunks.json, embeddings.pkl) are stored in the current working directory."
)   