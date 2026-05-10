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
st.title("📄 GSK Document Intelligence")
st.markdown(
    """
    Upload a **GSK Knowledge Article PDF** to check compliance with all mandatory guidelines.
    The app validates headings, tables, screenshots, notes, attachments, plain language,
    AQI checklist, and required sections (Audience, Prerequisites, Keywords, etc.).
    """
)

# ------------------------------------------------------------------
# Session state
# ------------------------------------------------------------------
if "article_text" not in st.session_state:
    st.session_state.article_text = None
if "image_count" not in st.session_state:
    st.session_state.image_count = 0

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
# Full compliance checker (updated with accurate sentence length)
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
# Main App
# ------------------------------------------------------------------
st.header("📄 Upload GSK Knowledge Article PDF")

article_file = st.file_uploader(
    "Choose the Knowledge Article PDF to verify",
    type=["pdf"],
    key="article_uploader",
)

if article_file is not None:
    with st.spinner("Extracting article text and detecting images..."):
        text, img_count = extract_text_and_images(article_file)
        if not text.strip():
            st.error("No text could be extracted from the PDF. Please check the file.")
        else:
            st.session_state.article_text = text
            st.session_state.image_count = img_count
            st.success(f"Article text extracted successfully. Detected {img_count} embedded image(s) in the PDF.")

# Run compliance analysis if we have article text
if st.session_state.article_text is not None:
    st.markdown("---")
    st.subheader("🔍 Full Compliance Analysis (All Guidelines)")
    with st.spinner("Running all rule checks..."):
        results = check_article_compliance(
            st.session_state.article_text,
            has_images=(st.session_state.image_count > 0)
        )
    st.write(f"### Total rules evaluated: {len(results)}")
    for r in results:
        with st.expander(f"{r['status']} {r['rule']}"):
            st.write(r["explanation"])
    st.write("### 🧾 Overall Summary")
    client = load_inference_client()
    summary = generate_summary_from_results(results, client)
    st.success(summary)
    report_text = "\n\n".join(
        f"{r['status']} {r['rule']}\n{r['explanation']}" for r in results
    )
    st.download_button(
        "Download Full Report",
        data=report_text,
        file_name="compliance_report.txt",
        mime="text/plain",
    )
else:
    st.info("Please upload a PDF to begin compliance checking.")

st.markdown("---")
st.caption("Compliance validation based on GSK Knowledge Article Guidelines. Image detection uses actual PDF image streams; sentence length uses only extracted article content with custom sentence tokenizer.")