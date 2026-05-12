import re

def clean_article_text(raw_text: str) -> str:
    """
    Extract only the real knowledge article content from SECTION 2.
    Returns a string with clean sentences suitable for readability analysis.
    """
    match = re.search(r"SECTION 2: FULL TEXT EXTRACTION(.*?)(?:SECTION 3:|$)", raw_text, re.DOTALL | re.IGNORECASE)
    if not match:
        match = re.search(r"SECTION 2:.*?\n(.*?)(?:SECTION \d+:|$)", raw_text, re.DOTALL | re.IGNORECASE)
    if not match:
        return ""

    content = match.group(1)
    lines = content.splitlines()
    cleaned_lines = []

    skip_patterns = [
        r"^##\s*\[.*\]$",
        r"^#\s*$",
        r"^---+$",
        r"^\*\s*\(Note:.*\)\*$",
        r"^\* \(This is a button.*\) \*$",
        r"^\[.*\]$",
        r"^> \*\(Dark pill.*\)\*$",
        r"^text\[.*\]$",
        r"^\|\s*-+\s*\|",
        r"^\s*\*$",
    ]

    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue

        skip = False
        for pat in skip_patterns:
            if re.match(pat, stripped, re.IGNORECASE):
                skip = True
                break
        if skip:
            continue

        if stripped.startswith(">"):
            stripped = stripped[1:].strip()

        stripped = re.sub(r"\*\*([^*]+)\*\*", r"\1", stripped)
        stripped = re.sub(r"\*([^*]+)\*", r"\1", stripped)
        stripped = re.sub(r"[^\w\s\.\,\!\?\;\:\-\(\)]", " ", stripped)
        stripped = re.sub(r"\s+", " ", stripped).strip()

        if stripped and len(stripped) > 1:
            cleaned_lines.append(stripped)

    text_block = " ".join(cleaned_lines)
    text_block = re.sub(r"\.\s+", ". ", text_block)
    text_block = re.sub(r"\s+", " ", text_block).strip()

    return text_block