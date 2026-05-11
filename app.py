import streamlit as st
import fitz  # PyMuPDF
import os
import re
from dotenv import load_dotenv
import pdfplumber
import io
from huggingface_hub import InferenceClient
import textstat

# ------------------------------------------------------------------
# Environment & config
# ------------------------------------------------------------------
load_dotenv()
if os.getenv("HF_TOKEN"):
    os.environ["HF_TOKEN"] = os.getenv("HF_TOKEN")

st.set_page_config(page_title="GSK Document Intelligence", layout="wide")

# ------------------------------------------------------------------
# Custom CSS for light mode, GSK orange containers, info/success colours, and button styles
# ------------------------------------------------------------------
st.markdown(
    """
    <style>
    /* Light mode background and text – main page now white */
    .stApp {
        background-color: white;
        color: #31333F;
    }

    /* Keep the sidebar grey (#f0f2f6) */
    section[data-testid="stSidebar"] {
        background-color: #f0f2f6 !important;
    }

    /* Expander header (summary) styling: GSK orange, white text */
    div[data-testid="stExpander"] details summary {
        background-color: #F36633 !important;
        color: white !important;
        border-radius: 4px;
        padding: 8px 12px;
        font-weight: bold;
    }
    /* Expander content area: white background, black text */
    div[data-testid="stExpander"] details div[data-testid="stExpanderDetails"] {
        background-color: white !important;
        color: #31333F !important;
        padding: 12px;
    }

    /* Recolour all info/success/warning notifications to #f29d80 */
    div.stAlert {
        background-color: #f29d80 !important;
        color: white !important;
        border-color: #f29d80 !important;
    }
    /* Ensure text inside alerts is white and legible */
    div.stAlert p, div.stAlert span, div.stAlert div {
        color: white !important;
    }

    /* Style the file upload button (Browse files) */
    input[type="file"]::file-selector-button {
        background-color: #F36633 !important;
        color: white !important;
        border: 1px solid #F36633 !important;
        border-radius: 4px;
        padding: 4px 12px;
        font-weight: bold;
    }
    /* Optional: hover effect for the upload button */
    input[type="file"]::file-selector-button:hover {
        background-color: #e0552a !important;
        border-color: #e0552a !important;
    }

    /* Style primary buttons (including download button now set as primary) */
    button[kind="primary"] {
        background-color: #F36633 !important;
        color: white !important;
        border-color: #F36633 !important;
    }
    button[kind="primary"]:hover {
        background-color: #e0552a !important;
        border-color: #e0552a !important;
        color: white !important;
    }
    /* Force each tab panel to be a scrollable white container */
    div[data-testid="stTabs"] div[role="tabpanel"] {
        max-height: 300px !important;     /* adjust height (or use 60vh) */
        overflow-y: auto !important;
        background-color: white !important;
        padding: 15px 20px !important;    /* top/bottom & left/right */
        border-radius: 4px;
        box-shadow: 0 2px 8px rgba(0,0,0,0.08);  /* subtle shadow for depth */
        margin-top: 0;
    }/* Equal-width tabs */
    div[data-testid="stTabs"] [role="tablist"] {
        display: grid !important;
        grid-template-columns: 1fr 1fr 1fr;
        width: 100%;
    }

    div[data-testid="stTabs"] [role="tablist"] button[role="tab"] {
        width: 100% !important;
        text-align: center;
        justify-content: center;   /* centers tab text horizontally */
    }
    [data-testid="stHeader"] {
        display: none;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

# Near the top of the file, after the existing custom CSS block, add:
st.markdown(
    """
    <style>
    /* Sidebar buttons – GSK orange with white text */
    section[data-testid="stSidebar"] button[kind="secondary"],
    section[data-testid="stSidebar"] button[kind="primary"] {
        background-color: #F36633 !important;
        color: white !important;
        border-color: #F36633 !important;
        width: 100%;
        text-align: left;
        padding: 0.5rem;
        margin-bottom: 0.2rem;
    }
    section[data-testid="stSidebar"] button[kind="secondary"]:hover,
    section[data-testid="stSidebar"] button[kind="primary"]:hover {
        background-color: #e0552a !important;
        color: white !important;
    }
    /* Active (selected) button darker border or slight shadow */
    section[data-testid="stSidebar"] button[kind="primary"].selected-button {
        border: 2px solid white;
        font-weight: bold;
    }
    </style>
    """,
    unsafe_allow_html=True,
)

def shorten_filename(filename: str, first=5, last=7) -> str:
    """
    Return a shortened display name without the .pdf extension.
    
    Examples:
    - "document.pdf" -> "document"
    - "verylongfilename.pdf" -> "veryl...name"
    """

    # Remove .pdf extension if present
    name = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)

    # Keep original if length is 9 characters or fewer
    if len(name) <= 9:
        return name

    # Shorten long filenames
    return f"{name[:first]}...{name[-last:]}"

# ------------------------------------------------------------------
# Logo section (add a logo.png file in the same directory)
# ------------------------------------------------------------------
st.image("GSK_LOGO.png", width=150)

# ------------------------------------------------------------------
# Session state initialisation for multiple files
# ------------------------------------------------------------------
if "processed_files" not in st.session_state:
    st.session_state.processed_files = {}   # key = filename, value = {"text":..., "image_count":..., "results":...}
if "selected_file" not in st.session_state:
    st.session_state.selected_file = None

# ------------------------------------------------------------------
# PDF text extraction + image count detection
# ------------------------------------------------------------------
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

# ------------------------------------------------------------------
# Robust article content extractor (removes all forensic markup)
# ------------------------------------------------------------------
def clean_article_text(raw_text: str) -> str:
    """
    Extract only the real knowledge article content from SECTION 2.
    Returns a string with clean sentences suitable for readability analysis.
    """
    # Step 1: Isolate SECTION 2 (Full Text Extraction)
    match = re.search(r"SECTION 2: FULL TEXT EXTRACTION(.*?)(?:SECTION 3:|$)", raw_text, re.DOTALL | re.IGNORECASE)
    if not match:
        # Fallback: try to find any content after "SECTION 2"
        match = re.search(r"SECTION 2:.*?\n(.*?)(?:SECTION \d+:|$)", raw_text, re.DOTALL | re.IGNORECASE)
    if not match:
        # If no SECTION 2, return empty (but we'll fallback to original)
        return ""

    content = match.group(1)

    # Step 2: Split into lines and clean
    lines = content.splitlines()
    cleaned_lines = []

    # Patterns to remove (forensic markers)
    skip_patterns = [
        r"^##\s*\[.*\]$",           # ## [ARTICLE TITLE], ## [SECTION HEADING 1]
        r"^#\s*$",                  # lone '#'
        r"^---+$",                  # horizontal rule
        r"^\*\s*\(Note:.*\)\*$",    # *(Note: ...)*
        r"^\* \(This is a button.*\) \*$",
        r"^\[.*\]$",                # [BUTTON TEXT], [TABLE - ...]
        r"^> \*\(Dark pill.*\)\*$",
        r"^text\[.*\]$",            # text[[108, 366,...]]
        r"^\|\s*-+\s*\|",           # table separator line |---|
        r"^\s*\*$",                 # lone asterisk
    ]

    for line in lines:
        stripped = line.strip()
        # Skip empty lines? Keep for sentence separation but will be normalized later.
        if not stripped:
            continue

        # Skip if matches any forensic pattern
        skip = False
        for pat in skip_patterns:
            if re.match(pat, stripped, re.IGNORECASE):
                skip = True
                break
        if skip:
            continue

        # Remove leading "> " if present (used for quoted text)
        if stripped.startswith(">"):
            stripped = stripped[1:].strip()

        # Remove markdown bold/italic but keep text
        stripped = re.sub(r"\*\*([^*]+)\*\*", r"\1", stripped)
        stripped = re.sub(r"\*([^*]+)\*", r"\1", stripped)

        # Remove any remaining special characters that aren't sentence delimiters
        # But keep periods, commas, spaces, letters, numbers, and basic punctuation.
        stripped = re.sub(r"[^\w\s\.\,\!\?\;\:\-\(\)]", " ", stripped)
        # Collapse multiple spaces
        stripped = re.sub(r"\s+", " ", stripped).strip()

        if stripped and len(stripped) > 1:  # ignore single characters
            cleaned_lines.append(stripped)

    # Join into a single block of text
    text_block = " ".join(cleaned_lines)

    # Normalize spacing around periods for sentence splitting
    text_block = re.sub(r"\.\s+", ". ", text_block)
    text_block = re.sub(r"\s+", " ", text_block).strip()

    return text_block

# ------------------------------------------------------------------
# Accurate sentence count (handles abbreviations)
# ------------------------------------------------------------------
def count_sentences(text: str) -> int:
    """
    Count sentences using a more robust approach: split on '.', '!', '?'
    but avoid splitting on common abbreviations (e.g., 'e.g.', 'i.e.').
    This is a simplified version; for extreme accuracy we could use nltk,
    but this works for typical article text.
    """
    # Replace common abbreviations with a placeholder that won't be split
    abbrev = re.compile(r'\b(?:e\.g|i\.e|vs\.|etc\.|Mr\.|Ms\.|Dr\.|Prof\.|Ltd\.|Inc\.|Corp\.)\b', re.IGNORECASE)
    text = abbrev.sub(lambda m: m.group(0).replace('.', '@@@'), text)
    # Split on . ! ? followed by space or end of string
    sentences = re.split(r'[.!?]\s+', text)
    # Restore abbreviations
    sentences = [s.replace('@@@', '.') for s in sentences]
    # Filter out empty strings
    sentences = [s for s in sentences if s.strip()]
    return len(sentences)

# ------------------------------------------------------------------
# Full compliance checker (unchanged logic)
# ------------------------------------------------------------------
def check_article_compliance(article_text: str, has_images: bool) -> list:
    """
    Run all rule‑based checks against the article text.
    has_images: True if PDF contains at least one embedded image.
    Returns a list of dicts: {rule, status, explanation}
    """
    rules = []
    text_lower = article_text.lower()
    
    # For readability rules, use the cleaned version (forensic markup removed)
    cleaned_text = clean_article_text(article_text)
    
    # ----- 1. Mandatory feedback callout (QUESTION type) -----
    target_phrase = (
        "Did this article meet your needs? "
        "Click Yes to let us know! If No, please share what's missing so we can improve the content."
    )
    if target_phrase in article_text:
        rules.append({"rule": "Feedback callout (QUESTION type)", "status": "✅ Followed", "explanation": "The mandatory feedback callout phrase is present."})
    else:
        rules.append({"rule": "Feedback callout (QUESTION type)", "status": "❌ Violated", "explanation": "Exact phrase not found. Must appear at end of article."})

    # ----- 2. Table header orange background + bold white text -----
    if re.search(r"orange\s*background.*bold\s*white", article_text, re.IGNORECASE):
        rules.append({"rule": "Table header: orange background + bold white text", "status": "✅ Followed", "explanation": "Matches guideline (#F36633)."})
    elif re.search(r"grey tint|no colour background|dark\s*text", article_text, re.IGNORECASE):
        rules.append({"rule": "Table header: orange background + bold white text", "status": "❌ Violated", "explanation": "Header uses grey/dark text, not orange background."})
    else:
        rules.append({"rule": "Table header: orange background + bold white text", "status": "⚠️ Undetermined", "explanation": "Could not verify header styling."})

    # ----- 3. HEADING LEVELS (Core: Heading 2 as default) -----
    heading2_used = re.search(r"Heading 2|Heading\s*2", article_text, re.IGNORECASE)
    heading1_used = re.search(r"Heading 1|Heading\s*1", article_text, re.IGNORECASE)
    if heading2_used and not heading1_used:
        rules.append({"rule": "Heading levels: Heading 2 is default", "status": "✅ Followed", "explanation": "Article uses Heading 2 as main level (no Heading 1)."})
    elif heading1_used and not heading2_used:
        rules.append({"rule": "Heading levels: Heading 2 is default", "status": "❌ Violated", "explanation": "Heading 1 is used but Heading 2 is missing. Use Heading 2 for main sections."})
    elif heading1_used and heading2_used:
        rules.append({"rule": "Heading levels: Heading 2 is default", "status": "⚠️ Warning", "explanation": "Both Heading 1 and Heading 2 present. Ensure Heading 1 is only for very large sections."})
    else:
        rules.append({"rule": "Heading levels: Heading 2 is default", "status": "⚠️ Undetermined", "explanation": "No heading level mentioned in article text."})

    # Avoid generic headings
    if re.search(r"Heading.*?Introduction|^Introduction$", article_text, re.MULTILINE):
        rules.append({"rule": "Headings are descriptive (avoid 'Introduction')", "status": "❌ Violated", "explanation": "Found generic heading 'Introduction'. Use specific titles like 'What is X?'"})
    else:
        rules.append({"rule": "Headings are descriptive (avoid 'Introduction')", "status": "✅ Followed", "explanation": "No generic headings detected."})

    # No numbers in headings
    if re.search(r"^\d+\.\s+\w+", article_text, re.MULTILINE):
        rules.append({"rule": "Headings have no numbers", "status": "❌ Violated", "explanation": "Numbered headings found (e.g., '1. Section'). Remove numbers."})
    else:
        rules.append({"rule": "Headings have no numbers", "status": "✅ Followed", "explanation": "No numbered headings."})

    # ----- 4. Description section -----
    if re.search(r"Description.*?\n", article_text) and "This Knowledge Article" in article_text:
        rules.append({"rule": "Article contains a Description section", "status": "✅ Followed", "explanation": "Starts with 'This Knowledge Article...'"})
    else:
        rules.append({"rule": "Article contains a Description section", "status": "❌ Violated", "explanation": "Missing Description section."})

    # ----- 5. Audience section (fixed regex) -----
    if re.search(r"\bAudience\s*[:|]?\b", article_text, re.IGNORECASE):
        rules.append({"rule": "Audience section present", "status": "✅ Followed", "explanation": "Clearly states intended audience."})
    else:
        rules.append({"rule": "Audience section present", "status": "❌ Violated", "explanation": "Every article must define its audience (e.g., 'All Employees, Managers, specific regions')."})

    # ----- 6. Prerequisites / "Access to" (fixed regex) -----
    if re.search(r"Prerequisites?\s*[:|]?|\bAccess to\b", article_text, re.IGNORECASE):
        rules.append({"rule": "Prerequisites / 'Access to' section", "status": "✅ Followed", "explanation": "Lists required access or prep."})
    else:
        rules.append({"rule": "Prerequisites / 'Access to' section", "status": "⚠️ Warning", "explanation": "Not explicitly mentioned. Recommended for instructional articles."})

    # ----- 7. Instructions use numbered list -----
    if re.search(r"\d+\.\s+\w+", article_text) and "numbered list" in text_lower:
        rules.append({"rule": "Instructions use numbered list", "status": "✅ Followed", "explanation": "Numbered steps detected."})
    elif re.search(r"\d+\.\s+\w+", article_text):
        rules.append({"rule": "Instructions use numbered list", "status": "✅ Followed", "explanation": "Numbered steps present."})
    else:
        rules.append({"rule": "Instructions use numbered list", "status": "⚠️ Undetermined", "explanation": "No numbered steps found; if tutorial, use numbered list."})

    # ----- 8. Contacts for Further Help -----
    if re.search(r"Contacts? for Further Help", article_text, re.IGNORECASE):
        rules.append({"rule": "Contacts for Further Help section", "status": "✅ Followed", "explanation": "Present."})
    else:
        rules.append({"rule": "Contacts for Further Help section", "status": "❌ Violated", "explanation": "Mandatory section missing."})

    # ----- 9. Keywords (30 semicolon‑separated) -----
    keywords_match = re.search(r"Keywords\s*[:|]\s*([^;]+(?:;\s*[^;]+)+)", article_text, re.IGNORECASE)
    if keywords_match:
        kw_text = keywords_match.group(1)
        kw_list = re.split(r';\s*', kw_text)
        if len(kw_list) >= 30:
            rules.append({"rule": "Keywords (30 semicolon‑separated)", "status": "✅ Followed", "explanation": f"Found {len(kw_list)} keywords."})
        else:
            rules.append({"rule": "Keywords (30 semicolon‑separated)", "status": "❌ Violated", "explanation": f"Only {len(kw_list)} keywords, need 30."})
    else:
        rules.append({"rule": "Keywords (30 semicolon‑separated)", "status": "❌ Violated", "explanation": "No Keywords section found."})

    # ----- 10. Hyperlinks blue & underlined -----
    if "blue" in text_lower and "underline" in text_lower:
        rules.append({"rule": "Hyperlinks are blue and underlined", "status": "✅ Followed", "explanation": "Matches system default."})
    else:
        rules.append({"rule": "Hyperlinks are blue and underlined", "status": "⚠️ Undetermined", "explanation": "Not explicitly stated."})

    # ----- 11. Copy Link button -----
    if "Copy Link" in article_text:
        rules.append({"rule": "Copy Link button visible", "status": "✅ Followed", "explanation": "Mentioned."})
    else:
        rules.append({"rule": "Copy Link button visible", "status": "❌ Violated", "explanation": "Must instruct to use Copy Link button."})

    # ----- 12. Table cell text uses Paragraph style -----
    if re.search(r"Paragraph.*style.*table|table.*Paragraph.*style", article_text, re.IGNORECASE):
        rules.append({"rule": "Table cell text uses Paragraph style", "status": "✅ Followed", "explanation": "Not Heading."})
    else:
        rules.append({"rule": "Table cell text uses Paragraph style", "status": "⚠️ Warning", "explanation": "Not clearly described; ensure table cells use Paragraph."})

    # ----- 13. Table: no copying from external sources -----
    if re.search(r"do not copy a table|paste as plain text|clear formatting", article_text, re.IGNORECASE):
        rules.append({"rule": "Table not copied from external sources", "status": "✅ Followed", "explanation": "Guideline followed."})
    else:
        rules.append({"rule": "Table not copied from external sources", "status": "⚠️ Warning", "explanation": "No mention of avoiding paste from Word/PDF."})

    # ----- 14. Table not imported as image -----
    if re.search(r"do not import.*table.*image", article_text, re.IGNORECASE):
        rules.append({"rule": "Table not imported as image", "status": "✅ Followed", "explanation": "Explicitly avoided."})
    else:
        rules.append({"rule": "Table not imported as image", "status": "⚠️ Warning", "explanation": "No statement; ensure table is real HTML table."})

    # ----- 15. Table Type 2: alternating row background -----
    if re.search(r"alternating.*row|#FAE2D5|light orange.*background", article_text, re.IGNORECASE):
        rules.append({"rule": "Table Type 2: alternating row background (#FAE2D5)", "status": "✅ Followed", "explanation": "Alternating rows used."})
    else:
        rules.append({"rule": "Table Type 2: alternating row background (#FAE2D5)", "status": "⚠️ Undetermined", "explanation": "Not described; only needed if using comparative tables."})

    # ----- 16. Table border colour (#F1A983 for Type 2) -----
    if re.search(r"#F1A983|border.*light orange", article_text, re.IGNORECASE):
        rules.append({"rule": "Table Type 2 border colour (#F1A983)", "status": "✅ Followed", "explanation": "Correct border colour."})
    else:
        rules.append({"rule": "Table Type 2 border colour (#F1A983)", "status": "⚠️ Undetermined", "explanation": "Not specified."})

    # ----- 17. Screenshot max width 850px (conditional on actual images) -----
    if has_images:
        if re.search(r"width.*850|max.*850px", article_text, re.IGNORECASE):
            rules.append({"rule": "Screenshot max width 850px", "status": "✅ Followed", "explanation": "Width specified or implied."})
        else:
            rules.append({"rule": "Screenshot max width 850px", "status": "⚠️ Warning", "explanation": "Not mentioned; ensure images are ≤850px wide."})
    else:
        rules.append({"rule": "Screenshot max width 850px", "status": "⚠️ Not applicable", "explanation": "No embedded images detected in PDF. No screenshots to check."})

    # ----- 18. Screenshots have alt text (conditional on actual images) -----
    if has_images:
        if re.search(r"Alternative description|alt text", article_text, re.IGNORECASE):
            rules.append({"rule": "Screenshots have alt text", "status": "✅ Followed", "explanation": "Alt text described."})
        else:
            rules.append({"rule": "Screenshots have alt text", "status": "❌ Violated", "explanation": "Every image must have alt text (Alternative description field)."})
    else:
        rules.append({"rule": "Screenshots have alt text", "status": "⚠️ Not applicable", "explanation": "No embedded images detected in PDF. Alt text not required."})

    # ----- 19. Screenshot annotations use GSK orange (conditional on actual images) -----
    if has_images:
        if re.search(r"#f36633|orange.*annotation|GSK orange", article_text, re.IGNORECASE):
            rules.append({"rule": "Screenshot annotations use GSK orange", "status": "✅ Followed", "explanation": "Matches brand colour."})
        else:
            rules.append({"rule": "Screenshot annotations use GSK orange", "status": "⚠️ Warning", "explanation": "No mention of annotation colour; use #f36633."})
    else:
        rules.append({"rule": "Screenshot annotations use GSK orange", "status": "⚠️ Not applicable", "explanation": "No embedded images detected in PDF. No screenshots to annotate."})

    # ----- 20. Critical info not only in images -----
    if re.search(r"text version|summary.*below|accessible to screen readers", article_text, re.IGNORECASE):
        rules.append({"rule": "Critical info not only in images", "status": "✅ Followed", "explanation": "Provides text alternative."})
    else:
        rules.append({"rule": "Critical info not only in images", "status": "⚠️ Warning", "explanation": "No text alternative mentioned; ensure critical data is also in text."})

    # ----- 21. Note formatting: bold "Note:" + Paragraph -----
    note_format = re.search(r"Note:\s*\*\*?|bold.*Note:|Note:.*bold", article_text, re.IGNORECASE)
    if note_format:
        rules.append({"rule": "Note formatting: bold 'Note:' + Paragraph", "status": "✅ Followed", "explanation": "Correctly formatted."})
    else:
        rules.append({"rule": "Note formatting: bold 'Note:' + Paragraph", "status": "⚠️ Warning", "explanation": "Notes should have 'Note:' in bold, rest normal."})

    # ----- 22. Attachment names contain no dates -----
    if re.search(r"\b(19|20)\d{2}\b", article_text) and "attachment" in text_lower:
        rules.append({"rule": "Attachment names contain no dates", "status": "❌ Violated", "explanation": "Found year number in attachment description. Do not include dates (e.g., '2024')."})
    else:
        rules.append({"rule": "Attachment names contain no dates", "status": "✅ Followed", "explanation": "No dates detected in attachment names."})

    # ----- 23. Attachment name matches link text (consistency) -----
    if re.search(r"identical name|same name.*attachment.*link", article_text, re.IGNORECASE):
        rules.append({"rule": "Attachment name matches link text", "status": "✅ Followed", "explanation": "Consistency mentioned."})
    else:
        rules.append({"rule": "Attachment name matches link text", "status": "⚠️ Warning", "explanation": "Ensure the linked text and file name are identical."})

    # ----- 24. Attachments are supplementary, not primary -----
    if re.search(r"must not serve as the primary source|complement the main content", article_text, re.IGNORECASE):
        rules.append({"rule": "Attachments are supplementary, not primary", "status": "✅ Followed", "explanation": "Guideline followed."})
    else:
        rules.append({"rule": "Attachments are supplementary, not primary", "status": "⚠️ Warning", "explanation": "No statement; ensure article is self‑contained."})

    # ----- 25. Plain language: short sentences (using cleaned text and custom sentence counter) -----
    if cleaned_text:
        sentence_count = count_sentences(cleaned_text)
        total_words = len(cleaned_text.split())
        if sentence_count > 0:
            avg_len = total_words / sentence_count
            if avg_len < 20:
                rules.append({"rule": "Plain language: short sentences (average <20 words)", "status": "✅ Followed", "explanation": f"Average sentence length {avg_len:.1f} words (based on extracted article content)."})
            else:
                rules.append({"rule": "Plain language: short sentences (average <20 words)", "status": "❌ Violated", "explanation": f"Average {avg_len:.1f} words – too long (based on extracted article content)."})
        else:
            rules.append({"rule": "Plain language: short sentences", "status": "⚠️ Undetermined", "explanation": "Could not compute sentence count from article content."})
    else:
        rules.append({"rule": "Plain language: short sentences", "status": "⚠️ Undetermined", "explanation": "No clean article content found for readability analysis."})

    # ----- 26. Plain language: active voice (heuristic) – also use cleaned text -----
    if cleaned_text:
        passive_patterns = r"\b(am|are|is|was|were|be|been|being)\s+(\w+ed|\w+en)\b"
        passive_matches = len(re.findall(passive_patterns, cleaned_text, re.IGNORECASE))
        if passive_matches < 5:
            rules.append({"rule": "Plain language: active voice preferred", "status": "✅ Followed", "explanation": f"Only {passive_matches} passive constructions in article content."})
        else:
            rules.append({"rule": "Plain language: active voice preferred", "status": "⚠️ Warning", "explanation": f"{passive_matches} passive phrases found; rewrite to active where possible."})
    else:
        rules.append({"rule": "Plain language: active voice preferred", "status": "⚠️ Undetermined", "explanation": "No clean article content available."})

    # ----- 27. Spacing: no blank line after heading -----
    if re.search(r"(Heading 2|^#+\s+.*)\n\s*\n\s*\w", article_text, re.MULTILINE):
        rules.append({"rule": "Spacing: no blank line after heading", "status": "❌ Violated", "explanation": "Blank line found after heading – should be no gap."})
    else:
        rules.append({"rule": "Spacing: no blank line after heading", "status": "✅ Followed", "explanation": "No incorrect spacing detected."})

    # One blank line between sections (optional)
    if re.search(r"Section.*?\n\s*\n.*?Section", article_text, re.DOTALL | re.IGNORECASE):
        rules.append({"rule": "Spacing: one blank line between sections", "status": "✅ Followed", "explanation": "Sections separated by blank line."})
    else:
        rules.append({"rule": "Spacing: one blank line between sections", "status": "⚠️ Warning", "explanation": "Not clearly separated; use one line of space."})

    # ----- 28. AQI checklist items (10 rules summarised) -----
    aqi_checks = {
        "Is the article unique? (no duplicates)": r"\bunique\b|\bduplicate\b",
        "Is the article accurate and relevant?": r"\baccurate\b|\brelevant\b|\bup to date\b",
        "Is the article complete? (all steps, goal achieved)": r"\bcomplete\b|\ball steps\b",
        "Is the title correct? (descriptive, concise)": r"\btitle.*descriptive\b|\bconcise title\b",
        "Does it follow readability guidelines?": r"\breadability\b|\bplain language\b",
        "Are the links valid?": r"\blinks.*valid\b|\bworking links\b",
        "Are the user / security correct?": r"\buser criteria\b|\bcan read\b",
        "Is the Knowledge Base & category accurate?": r"\bknowledge base\b|\bcategory\b",
        "Has proper metadata been entered?": r"\bmetadata\b|\bkeywords\b|\bassignment group\b",
        "Grammar / spelling checked?": r"\bgrammar\b|\bspelling\b"
    }
    for check, pattern in aqi_checks.items():
        if re.search(pattern, article_text, re.IGNORECASE):
            rules.append({"rule": f"AQI: {check}", "status": "✅ Followed", "explanation": "Mentioned."})
        else:
            rules.append({"rule": f"AQI: {check}", "status": "⚠️ Warning", "explanation": "Not explicitly addressed."})

    # ----- 29. Missing Information section (if outdated) -----
    if re.search(r"Missing Information", article_text):
        rules.append({"rule": "Missing Information section present (if outdated content)", "status": "✅ Followed", "explanation": "Has a section for outdated info."})
    else:
        rules.append({"rule": "Missing Information section present (if outdated content)", "status": "⚠️ Undetermined", "explanation": "Not needed if all information is up to date."})

    # ----- 30. Callout line breaks use Shift+Enter -----
    if re.search(r"Shift\s*\+\s*Enter", article_text):
        rules.append({"rule": "Callout line breaks use Shift+Enter", "status": "✅ Followed", "explanation": "Correct line break method."})
    else:
        rules.append({"rule": "Callout line breaks use Shift+Enter", "status": "⚠️ Info", "explanation": "Not mentioned; use Shift+Enter to add new lines inside callouts."})

    return rules

# ------------------------------------------------------------------
# LLM summary generator (unchanged)
# ------------------------------------------------------------------
@st.cache_resource
def load_inference_client():
    token = os.getenv("HF_TOKEN")
    if not token:
        st.error("HF_TOKEN not found. Set it in .env.")
        st.stop()
    return InferenceClient(token=token)

def generate_summary_from_results(results: list, client) -> str:
    findings = ""
    for r in results:
        findings += f"- {r['status']} {r['rule']}: {r['explanation']}\n"
    prompt = f"""You are a compliance analyst. Given the following rule‑check results for a GSK Knowledge Article, write a short, flowing paragraph (max 150 words) summarising the overall compliance, highlighting major violations and warnings. Use plain English.

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
        violated = [r for r in results if "Violated" in r["status"]]
        warnings = [r for r in results if "Warning" in r["status"]]
        summary = f"The article follows most rules but has {len(violated)} violations and {len(warnings)} warnings. "
        if violated:
            summary += "Violations: " + "; ".join([r["rule"] for r in violated[:5]]) + "."
        return summary

# ------------------------------------------------------------------
# Main App – Multi‑document upload
# ------------------------------------------------------------------
st.header("Upload GSK Knowledge Article PDFs")

# File uploader accepts multiple files
uploaded_files = st.file_uploader(
    """Upload one or more **GSK Knowledge Article PDFs** to check compliance.
    The app validates headings, tables, screenshots, notes, attachments, plain language,
    AQI checklist, and required sections (Audience, Prerequisites, Keywords, etc.).
    """,
    type=["pdf"],
    accept_multiple_files=True,
    key="article_uploader",
)

# Process each newly uploaded file ...
if uploaded_files:
    for file in uploaded_files:
        if file.name not in st.session_state.processed_files or True:
            with st.spinner(f"Processing {file.name}..."):
                text, img_count = extract_text_and_images(file)
                st.session_state.processed_files[file.name] = {
                    "text": text,
                    "image_count": img_count,
                    "results": None
                }

# 👇 INSERT THE DEFAULT SELECTION CODE HERE
file_names = list(st.session_state.processed_files.keys())
if file_names and (st.session_state.selected_file is None or st.session_state.selected_file not in file_names):
    st.session_state.selected_file = file_names[0]

# Sidebar – document selection buttons
st.sidebar.title("Uploaded Documents")
file_names = list(st.session_state.processed_files.keys())
selected_file = st.session_state.get("selected_file", None)

if file_names:
    if selected_file and selected_file in file_names:
        st.sidebar.success(f"Selected: {selected_file}")

    st.sidebar.markdown("---")
    for file in file_names:
        is_active = (selected_file == file)
        label = ("► " if is_active else "") + shorten_filename(file)
        # Use 'primary' type for the active file, 'secondary' for others to enable CSS distinction
        btn_type = "primary" if is_active else "secondary"
        if st.sidebar.button(label, key=f"btn_{file}", type=btn_type):
            st.session_state.selected_file = file
else:
    st.sidebar.info("No documents uploaded yet.")
# Main area – display results for the selected file
if selected_file and selected_file in st.session_state.processed_files:
    file_data = st.session_state.processed_files[selected_file]
    article_text = file_data["text"]
    image_count = file_data["image_count"]

    if not article_text.strip():
        st.error(f"No text could be extracted from {selected_file}. Please check the file.")
    else:
        st.subheader(f"Compliance Analysis: {selected_file}")

        # Compute results if not already done
        if file_data["results"] is None:
            with st.spinner("Running all rule checks..."):
                results = check_article_compliance(article_text, has_images=(image_count > 0))
            st.session_state.processed_files[selected_file]["results"] = results
        else:
            results = file_data["results"]

        passed = [r for r in results if "Followed" in r["status"]]
        warnings = [r for r in results if "Warning" in r["status"] or "Undetermined" in r["status"] or "Not applicable" in r["status"] or "Info" in r["status"]]
        violated = [r for r in results if "Violated" in r["status"]]

        tab1, tab2, tab3 = st.tabs([
            f"✅ Passed ({len(passed)})",
            f"⚠️ Warnings ({len(warnings)})",
            f"❌ Violated ({len(violated)})"
        ])

        with tab1:
            if passed:
                for r in passed:
                    with st.expander(f"{r['rule']}"):
                        st.write(r["explanation"])
            else:
                st.info("No passed guidelines found.")

        with tab2:
            if warnings:
                for r in warnings:
                    with st.expander(f"{r['rule']}"):
                        st.write(r["explanation"])
            else:
                st.info("No warnings or undetermined items.")

        with tab3:
            if violated:
                for r in violated:
                    with st.expander(f"{r['rule']}"):
                        st.write(r["explanation"])
            else:
                st.info("No violations – excellent!")

        st.write("### Summary")
        client = load_inference_client()
        summary = generate_summary_from_results(results, client)
        st.success(summary)

        report_text = "\n\n".join(
            f"{r['status']} {r['rule']}\n{r['explanation']}" for r in results
        )
        st.download_button(
            f"Download Report",
            data=report_text,
            file_name=f"compliance_report_{selected_file}.txt",
            mime="text/plain",
            type="primary",
        )
else:
    st.info("Please upload PDFs to begin compliance checking. Use the sidebar to select a document after uploading.")