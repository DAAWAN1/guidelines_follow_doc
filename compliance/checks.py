"""
compliance/checks.py
====================
GSK Document Intelligence – Accessibility & Inclusion Compliance Checks.

All public check functions accept a `doc_data` dict (from
extraction.extract_rich_docx_data) and/or a plain `text` string.

Each function returns a list of result dicts:
    {
        "rule":        str,   – short rule name shown in the UI
        "status":      str,   – one of STATUS_OK / STATUS_WARNING / STATUS_VIOLATED
        "explanation": str,   – human-readable detail
    }

Call run_all_checks() to execute every check at once.
"""

from __future__ import annotations
import re
from typing import Any

# ---------------------------------------------------------------------------
# Status labels (match whatever your existing UI expects)
# ---------------------------------------------------------------------------
STATUS_OK = "✅ OK"
STATUS_WARNING = "⚠️ Warning"
STATUS_VIOLATED = "❌ Violated"

# ---------------------------------------------------------------------------
# Sans-serif font set (must stay in sync with extraction.SANS_SERIF_FONTS)
# ---------------------------------------------------------------------------
SANS_SERIF_FONTS = {
    "arial", "helvetica", "calibri", "verdana", "tahoma",
    "trebuchet ms", "trebuchet", "franklin gothic", "gill sans",
    "open sans", "lato", "roboto", "noto sans", "segoe ui",
    "myriad pro", "futura", "century gothic", "optima",
    "lucida sans", "lucida grande", "ubuntu", "fira sans",
    "source sans pro", "nunito", "raleway", "poppins", "inter",
    "avenir", "proxima nova", "gotham", "brandon grotesque",
    "barlow", "dm sans", "work sans", "outfit",
}

# Bullet characters considered standard
STANDARD_BULLET_CHARS = {"•", "◦", "▪", "▸", "–", "-", "*", "○", "●"}

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _body_paragraphs(paragraphs: list[dict]) -> list[dict]:
    """Return only non-heading, non-title paragraphs with real text."""
    return [
        p for p in paragraphs
        if p["text"].strip()
        and not p["is_heading"]
        and not p["is_title"]
        and not p["is_caption"]
    ]


def _all_runs(paragraphs: list[dict]) -> list[dict]:
    """Flat list of all runs across all paragraphs."""
    return [run for p in paragraphs for run in p["runs"]]


def _word_count(text: str) -> int:
    return len(text.split())


def _is_url(text: str) -> bool:
    return bool(re.match(r"https?://\S+|www\.\S+", text.strip(), re.IGNORECASE))


# ---------------------------------------------------------------------------
# 1. Text alignment
# ---------------------------------------------------------------------------

def check_text_alignment(doc_data: dict) -> list[dict]:
    """
    Rule: Body copy must be left-aligned.
           Centred text is allowed only for headings/titles (used sparingly).
    """
    paragraphs = doc_data.get("paragraphs", [])
    violations = []
    for p in _body_paragraphs(paragraphs):
        if p["alignment"] in ("right", "center"):
            snippet = p["text"][:60].strip()
            violations.append(f'"{snippet}…" is {p["alignment"]}-aligned')

    if not violations:
        return [{"rule": "Text Alignment", "status": STATUS_OK,
                 "explanation": "All body copy is left- or justify-aligned."}]

    return [{"rule": "Text Alignment", "status": STATUS_VIOLATED,
             "explanation": (
                 f"Body text must be left-aligned. "
                 f"Found {len(violations)} non-left paragraph(s):\n"
                 + "\n".join(f"  • {v}" for v in violations[:5])
                 + ("\n  …and more." if len(violations) > 5 else "")
             )}]


# ---------------------------------------------------------------------------
# 2. Headings / titles / captions – no ALL CAPS, no italics
# ---------------------------------------------------------------------------

def check_heading_formatting(doc_data: dict) -> list[dict]:
    paragraphs = doc_data.get("paragraphs", [])
    bad = []

    for p in paragraphs:
        if not (p["is_heading"] or p["is_title"] or p["is_caption"]):
            continue
        text = p["text"].strip()
        if not text:
            continue

        # ---- Run-level checks (italic, all-caps) ----
        for run in p["runs"]:
            if not run["text"].strip():
                continue
            if run["italic"]:
                bad.append(f'[{p["style"]}] "{text[:50]}" – italic text')
            if run["all_caps"] or (run["text"] == run["text"].upper() and run["text"].isalpha()):
                bad.append(f'[{p["style"]}] "{text[:50]}" – all-caps text')

        # ---- Paragraph-level check: title case ----
        words = text.split()
        if len(words) > 2:
            # Count words that start with uppercase (excluding common short words)
            common_lower = {'and', 'of', 'the', 'to', 'for', 'with', 'on', 'at', 'by', 'in', 'a', 'an'}
            title_case_count = sum(1 for w in words if w and w[0].isupper() and w.lower() not in common_lower)
            if title_case_count > len(words) / 2:
                bad.append(f'[{p["style"]}] "{text[:50]}" – title case (use sentence case)')

    if not bad:
        return [{"rule": "Heading Formatting (No Caps/Italics)", "status": STATUS_OK,
                 "explanation": "No headings/titles/captions use all-caps or italics."}]

    return [{"rule": "Heading Formatting (No Caps/Italics)", "status": STATUS_VIOLATED,
             "explanation": (
                 "Headings, titles, and captions must not use italics or ALL CAPS:\n"
                 + "\n".join(f"  • {b}" for b in bad[:6])
                 + ("\n  …and more." if len(bad) > 6 else "")
             )}]


# ---------------------------------------------------------------------------
# 3. Underline – only for hyperlinks
# ---------------------------------------------------------------------------

def check_hyperlink_formatting(doc_data: dict) -> list[dict]:
    """
    Rule: Hyperlinks must not be bold or italic. Underline is allowed (and expected).
    """
    paragraphs = doc_data.get("paragraphs", [])
    violations = []

    for p in paragraphs:
        # First, collect all hyperlink display texts from the paragraph
        display_texts = [hl.get("display_text", "").strip() for hl in p["hyperlinks"] if hl.get("display_text", "").strip()]
        
        # Now examine each run that is underlined
        for run in p["runs"]:
            run_text = run["text"].strip()
            if not run_text or not run.get("underline"):
                continue
            
            # Check if this underlined run is bold or italic
            is_bold = run.get("bold", False)
            is_italic = run.get("italic", False)
            
            if is_bold or is_italic:
                # Try to match this run to a hyperlink display text
                matched = False
                for disp in display_texts:
                    # Normalise both strings: remove common markers like ***, *, _, etc.
                    clean_run = run_text.strip('*_ ')
                    clean_disp = disp.strip('*_ ')
                    if clean_disp in clean_run or clean_run in clean_disp:
                        matched = True
                        break
                
                # If we found a match or the run is underlined (likely a hyperlink), flag it
                if matched or display_texts:  # if there are any hyperlinks in the paragraph
                    style_issues = []
                    if is_bold:
                        style_issues.append("bold")
                    if is_italic:
                        style_issues.append("italic")
                    violations.append(
                        f'Underlined text "{run_text[:40]}…" uses {" and ".join(style_issues)} (only underline permitted).'
                    )
    
    if not violations:
        return [{"rule": "Hyperlink Formatting (Hyperlinks:o Bold/Italic)", "status": STATUS_OK,
                 "explanation": "No hyperlinks use bold or italic styling – only underline (allowed)."}]
    
    # Violations exist – report them
    return [{"rule": "Hyperlink Formatting (No Bold/Italic)", "status": STATUS_VIOLATED,
             "explanation": (
                 f"Found {len(violations)} hyperlink(s) with prohibited bold/italic formatting:\n"
                 + "\n".join(f"  • {v}" for v in violations[:5])
                 + ("\n  …and more." if len(violations) > 5 else "")
             )}]


def check_underline_usage(doc_data: dict) -> list[dict]:
    """
    Rule: Do not use underlined text unless it is a hyperlink.
    """
    paragraphs = doc_data.get("paragraphs", [])
    issues = []

    for p in paragraphs:
        # Collect the display text of all actual hyperlinks in this paragraph
        hl_texts = {h["display_text"].strip().lower() for h in p["hyperlinks"]}

        for run in p["runs"]:
            if run["underline"] and run["text"].strip():
                run_text = run["text"].strip()
                # Ignore if this run is the text of a hyperlink
                if run_text.lower() not in hl_texts and not _is_url(run_text):
                    issues.append(f'"{run_text[:50]}" – underlined but not a hyperlink')

    if not issues:
        return [{"rule": "Underline (Hyperlinks Only)", "status": STATUS_OK,
                 "explanation": "Underline is only used for hyperlinks."}]

    return [{"rule": "Underline (Hyperlinks Only)", "status": STATUS_VIOLATED,
             "explanation": (
                 "Underline should only be used for hyperlinks. "
                 f"Found {len(issues)} instance(s):\n"
                 + "\n".join(f"  • {i}" for i in issues[:5])
             )}]


# ---------------------------------------------------------------------------
# 4. Sentence capitalisation – only first word + proper nouns
# ---------------------------------------------------------------------------

def check_sentence_capitalisation(doc_data: dict) -> list[dict]:
    """
    Rule: Capitalise only the first word of each sentence and proper nouns.
    Detects words that are fully uppercase mid-sentence (suggesting shouting
    or careless capitalisation) and sentences that do not start with a capital.
    Ignores short acronyms (≤4 chars) as they are likely intentional.
    """
    paragraphs = doc_data.get("paragraphs", [])
    issues: list[str] = []

    sentence_re = re.compile(r'(?<=[.!?])\s+')
    all_caps_word = re.compile(r'\b[A-Z]{5,}\b')  # 5+ consecutive capitals = suspicious

    for p in _body_paragraphs(paragraphs):
        text = p["text"].strip()
        if not text:
            continue
        sentences = sentence_re.split(text)
        for sent in sentences:
            sent = sent.strip()
            if not sent:
                continue
            # Does the sentence start with a capital (or digit)?
            if sent[0].isalpha() and not sent[0].isupper():
                snippet = sent[:60]
                issues.append(f'Sentence does not start with a capital: "{snippet}…"')
            # Detect suspicious all-caps words (excludes short acronyms)
            for match in all_caps_word.finditer(sent):
                word = match.group()
                issues.append(f'Possible unnecessary all-caps word: "{word}" in "{sent[:50]}…"')

    if not issues:
        return [{"rule": "Sentence Capitalisation", "status": STATUS_OK,
                 "explanation": "Capitalisation appears consistent with guidelines."}]

    return [{"rule": "Sentence Capitalisation", "status": STATUS_WARNING,
             "explanation": (
                 f"Found {len(issues)} possible capitalisation issue(s) "
                 "(first word of sentence + proper nouns only):\n"
                 + "\n".join(f"  • {i}" for i in issues[:6])
                 + ("\n  …and more." if len(issues) > 6 else "")
             )}]


# ---------------------------------------------------------------------------
# 5. Font size – minimum 12pt
# ---------------------------------------------------------------------------

def check_font_size(doc_data: dict) -> list[dict]:
    """
    Rule: Use text at a minimum size of 12pt.
    """
    paragraphs = doc_data.get("paragraphs", [])
    too_small: list[str] = []

    for p in paragraphs:
        for run in p["runs"]:
            text = run["text"].strip()
            if not text:
                continue
            size = run["font_size_pt"]
            if size is not None and size < 12:
                snippet = text[:40]
                too_small.append(
                    f'"{snippet}" – {size}pt in [{p["style"]}]'
                )

    if not too_small:
        default_size = doc_data.get("default_size")
        if default_size and default_size < 12:
            return [{"rule": "Font Size (≥ 12pt)", "status": STATUS_VIOLATED,
                     "explanation": f"Document default font size is {default_size}pt (minimum is 12pt)."}]
        return [{"rule": "Font Size (≥ 12pt)", "status": STATUS_OK,
                 "explanation": "All detected text is at least 12pt."}]

    return [{"rule": "Font Size (≥ 12pt)", "status": STATUS_VIOLATED,
             "explanation": (
                 f"Found {len(too_small)} run(s) smaller than 12pt:\n"
                 + "\n".join(f"  • {t}" for t in too_small[:6])
                 + ("\n  …and more." if len(too_small) > 6 else "")
             )}]


# ---------------------------------------------------------------------------
# 6. Sans-serif font
# ---------------------------------------------------------------------------

def check_font_family(doc_data: dict) -> list[dict]:
    """
    Rule: Use a Sans Serif font throughout the document.
    If font information is missing, issue a warning.
    """
    paragraphs = doc_data.get("paragraphs", [])
    serif_instances: list[str] = []
    unknown_font_instances: list[str] = []
    
    for p in paragraphs:
        for run in p["runs"]:
            text = run["text"].strip()
            if not text:
                continue
            is_ss = run.get("is_sans_serif")
            font_name = run.get("font_name")
            
            if is_ss is False:
                serif_instances.append(
                    f'"{text[:40]}" uses "{font_name}" [{p["style"]}]'
                )
            elif is_ss is None and font_name is not None:
                # font name exists but not in our sans-serif list – treat as serif
                serif_instances.append(
                    f'"{text[:40]}" uses "{font_name}" (unknown family) [{p["style"]}]'
                )
            elif is_ss is None and font_name is None:
                # completely unknown font – record as unknown
                if len(text) > 5:  # avoid tiny runs
                    unknown_font_instances.append(
                        f'"{text[:40]}" – font name unknown [{p["style"]}]'
                    )
    
    if serif_instances:
        unique = list(dict.fromkeys(serif_instances))
        return [{"rule": "Sans-Serif Font", "status": STATUS_VIOLATED,
                 "explanation": (
                     f"Found {len(unique)} run(s) using a serif or unknown font family:\n"
                     + "\n".join(f"  • {s}" for s in unique[:5])
                     + ("\n  …and more." if len(unique) > 5 else "")
                 )}]
    
    if unknown_font_instances:
        # At least one unknown font – likely the document is using a serif font like Cambria
        return [{"rule": "Sans-Serif Font", "status": STATUS_WARNING,
                 "explanation": (
                     "Font family could not be determined for some text. "
                     "Please ensure the document uses a sans-serif font (e.g., Arial, Calibri, Verdana). "
                     "If using Cambria or Times New Roman, this is a violation."
                 )}]
    
    return [{"rule": "Sans-Serif Font", "status": STATUS_OK,
             "explanation": "Document appears to use a sans-serif font."}]

# ---------------------------------------------------------------------------
# 7. Bullet points – used for lists; no non-standard characters
# ---------------------------------------------------------------------------

def check_bullet_usage(doc_data: dict, raw_text: str = "") -> list[dict]:
    """
    Rule: Use bullet points when creating lists.
          Do not use non-standard characters as bullets.
    """
    paragraphs = doc_data.get("paragraphs", [])
    results = []

    # 7a – Detect inline lists not formatted as bullet points
    #      Heuristic: 3+ consecutive short lines starting with digits or
    #      dashes but NOT using the List style.
    list_like_re = re.compile(r"^\s*(\d+[\.\)]\s+|[•\-–—]\s+).+")
    unformatted_list_count = 0
    for p in paragraphs:
        text = p["text"].strip()
        if not text:
            continue
        if list_like_re.match(text) and not p["is_list"]:
            unformatted_list_count += 1

    if unformatted_list_count > 2:
        results.append({
            "rule": "Bullet Point Usage",
            "status": STATUS_WARNING,
            "explanation": (
                f"Found {unformatted_list_count} paragraph(s) that look like "
                "list items but are not formatted as proper bullet/list styles. "
                "Use the List Bullet style for accessibility."
            ),
        })
    else:
        results.append({
            "rule": "Bullet Point Usage",
            "status": STATUS_OK,
            "explanation": "List paragraphs appear to use proper list formatting.",
        })

    # 7b – Non-standard bullet characters
    bad_bullets: list[str] = []
    for p in paragraphs:
        if not p["is_list"]:
            continue
        bc = p["bullet_char"]
        if bc and bc not in STANDARD_BULLET_CHARS:
            bad_bullets.append(f'"{bc}" in: "{p["text"][:50]}"')

        # Also check first character of runs for image/graphic bullets (len check)
        first_run_text = p["runs"][0]["text"].strip() if p["runs"] else ""
        if first_run_text and len(first_run_text) == 1:
            char = first_run_text
            if (
                ord(char) > 127
                and char not in STANDARD_BULLET_CHARS
                and not char.isalpha()
            ):
                bad_bullets.append(f'Non-standard bullet character U+{ord(char):04X} "{char}"')

    if bad_bullets:
        results.append({
            "rule": "Non-Standard Bullet Characters",
            "status": STATUS_VIOLATED,
            "explanation": (
                "Only standard bullet characters (•, –, -, ○, ▪, ▸) are permitted. "
                f"Found {len(bad_bullets)} issue(s):\n"
                + "\n".join(f"  • {b}" for b in bad_bullets[:5])
            ),
        })
    else:
        results.append({
            "rule": "Non-Standard Bullet Characters",
            "status": STATUS_OK,
            "explanation": "All detected bullets use standard characters.",
        })

    return results


# ---------------------------------------------------------------------------
# 8. Bold overuse – WARNING only (not violation)
# ---------------------------------------------------------------------------
# Algorithm: for each body paragraph with ≥20 words, if bold_words / total_words > 0.10
# (i.e. more than 1 bold word per 10 words, or ~5 in 50), flag as a warning.
# Headings and titles are excluded.

BOLD_RATIO_THRESHOLD = 0.10   # 10 % of words – (~5 in 50)
MIN_WORDS_FOR_BOLD_CHECK = 20 # ignore very short paragraphs
ITALIC_RATIO_THRESHOLD = 0.10   # 10%
MIN_WORDS_FOR_ITALIC_CHECK = 20

def check_italics_overuse(doc_data: dict) -> list[dict]:
    """
    Rule: Avoid overuse of italics in body text (advisory, treated as a warning).
    Italic words should not exceed ~10 % of a paragraph's word count.
    """
    paragraphs = doc_data.get("paragraphs", [])
    offenders = []

    for p in _body_paragraphs(paragraphs):   # only body text, not headings
        para_text = p["text"]
        total_words = _word_count(para_text)
        if total_words < MIN_WORDS_FOR_ITALIC_CHECK:
            continue

        italic_words = sum(
            _word_count(run["text"])
            for run in p["runs"]
            if run["italic"] and run["text"].strip()
        )
        ratio = italic_words / total_words if total_words else 0
        if ratio > ITALIC_RATIO_THRESHOLD:
            snippet = para_text[:60].strip()
            offenders.append(
                f'"{snippet}…" – {italic_words}/{total_words} words italic ({ratio:.0%})'
            )

    if not offenders:
        return [{"rule": "Italics Overuse", "status": STATUS_OK,
                 "explanation": "Italics are used sparingly within body paragraphs."}]

    return [{"rule": "Italics Overuse", "status": STATUS_WARNING,
             "explanation": (
                 f"Found {len(offenders)} paragraph(s) where italics exceed "
                 f"the ~{ITALIC_RATIO_THRESHOLD:.0%} guideline.\n"
                 + "\n".join(f"  • {o}" for o in offenders[:5])
                 + ("\n  …and more." if len(offenders) > 5 else "")
             )}]

def check_bold_overuse(doc_data: dict) -> list[dict]:
    """
    Rule: Avoid overuse of bold (advisory, treated as a warning).
    Bold words should not exceed ~10 % of a paragraph's word count.
    Headings and titles are excluded from this check.
    """
    paragraphs = doc_data.get("paragraphs", [])
    offenders: list[str] = []

    for p in _body_paragraphs(paragraphs):
        para_text = p["text"]
        total_words = _word_count(para_text)
        if total_words < MIN_WORDS_FOR_BOLD_CHECK:
            continue

        bold_words = sum(
            _word_count(run["text"])
            for run in p["runs"]
            if run["bold"] and run["text"].strip()
        )
        ratio = bold_words / total_words if total_words else 0
        if ratio > BOLD_RATIO_THRESHOLD:
            snippet = para_text[:60].strip()
            offenders.append(
                f'"{snippet}…" – {bold_words}/{total_words} words bold '
                f"({ratio:.0%})"
            )

    if not offenders:
        return [{"rule": "Bold Overuse", "status": STATUS_OK,
                 "explanation": "Bold is used sparingly within body paragraphs."}]

    return [{"rule": "Bold Overuse", "status": STATUS_WARNING,
             "explanation": (
                 f"Found {len(offenders)} paragraph(s) where bold exceeds "
                 f"the ~{BOLD_RATIO_THRESHOLD:.0%} guideline "
                 f"(≈ 5 bold words per 50-word paragraph). "
                 "Avoid overusing bold for emphasis:\n"
                 + "\n".join(f"  • {o}" for o in offenders[:5])
                 + ("\n  …and more." if len(offenders) > 5 else "")
             )}]


# ---------------------------------------------------------------------------
# 9. Italics overuse – WARNING only (not violation)
# ---------------------------------------------------------------------------
# Same algorithm as bold. Additionally, any italic text in headings is a VIOLATION
# (handled by check_heading_formatting), so here we only look at body text.

ITALIC_RATIO_THRESHOLD = 0.10
MIN_WORDS_FOR_ITALIC_CHECK = 20


def check_italics_overuse(doc_data: dict) -> list[dict]:
    """
    Rule: Avoid overuse of italics in body text (advisory, treated as a warning).
    Italic words should not exceed ~10 % of a paragraph's word count.
    """
    paragraphs = doc_data.get("paragraphs", [])
    offenders: list[str] = []

    for p in _body_paragraphs(paragraphs):
        para_text = p["text"]
        total_words = _word_count(para_text)
        if total_words < MIN_WORDS_FOR_ITALIC_CHECK:
            continue

        italic_words = sum(
            _word_count(run["text"])
            for run in p["runs"]
            if run["italic"] and run["text"].strip()
        )
        ratio = italic_words / total_words if total_words else 0
        if ratio > ITALIC_RATIO_THRESHOLD:
            snippet = para_text[:60].strip()
            offenders.append(
                f'"{snippet}…" – {italic_words}/{total_words} words italic '
                f"({ratio:.0%})"
            )

    if not offenders:
        return [{"rule": "Italics Overuse", "status": STATUS_OK,
                 "explanation": "Italics are used sparingly within body paragraphs."}]

    return [{"rule": "Italics Overuse", "status": STATUS_WARNING,
             "explanation": (
                 f"Found {len(offenders)} paragraph(s) where italics exceed "
                 f"the ~{ITALIC_RATIO_THRESHOLD:.0%} guideline. "
                 "Avoid overusing italics; use bold or structural emphasis instead:\n"
                 + "\n".join(f"  • {o}" for o in offenders[:5])
                 + ("\n  …and more." if len(offenders) > 5 else "")
             )}]


# ---------------------------------------------------------------------------
# 10. Hyperlink naming – no bare URLs as display text
# ---------------------------------------------------------------------------

def check_hyperlink_naming(doc_data: dict) -> list[dict]:
    """
    Rule: Hyperlinks should use a simple naming convention that adequately
          describes where it takes you. Don't display links just using URLs.
    """
    paragraphs = doc_data.get("paragraphs", [])
    bare_urls: list[str] = []

    for p in paragraphs:
        for hl in p["hyperlinks"]:
            display = hl.get("display_text", "").strip()
            url = hl.get("url", "").strip()
            # Flag if display text IS a URL or is empty
            if not display or _is_url(display):
                bare_urls.append(f'"{display or url}" → {url}')

        # Also scan runs for underlined text that looks like a raw URL
        # (catches hyperlinks whose relationships weren't captured)
        for run in p["runs"]:
            text = run["text"].strip()
            if run["underline"] and _is_url(text):
                if not any(text in h.get("display_text", "") for h in p["hyperlinks"]):
                    bare_urls.append(f'Bare URL as display text: "{text[:70]}"')

    if not bare_urls:
        return [{"rule": "Hyperlink Naming", "status": STATUS_OK,
                 "explanation": "All hyperlinks have descriptive display text."}]

    return [{"rule": "Hyperlink Naming", "status": STATUS_VIOLATED,
             "explanation": (
                 f"Found {len(bare_urls)} hyperlink(s) displaying raw URLs instead "
                 "of descriptive text:\n"
                 + "\n".join(f"  • {u}" for u in bare_urls[:5])
             )}]


# ---------------------------------------------------------------------------
# 11. Table of Contents – required for multi-page documents
# ---------------------------------------------------------------------------

def check_table_of_contents(doc_data: dict) -> list[dict]:
    """
    Rule: Contents and indexes are essential for documents with several
          pages or chapters (guideline threshold: > 4 pages).
    """
    page_count = doc_data.get("page_count", 1)
    has_toc = doc_data.get("has_toc", False)
    has_headings = any(
        p["is_heading"] for p in doc_data.get("paragraphs", [])
    )

    if has_headings and not has_toc:
        return [{"rule": "Table of Contents", "status": STATUS_WARNING,
                 "explanation": (
                     f"Document is approximately {page_count} page(s) with headings "
                     "but no Table of Contents was detected. "
                     "A TOC is recommended for accessibility in longer documents."
                 )}]

    return [{"rule": "Table of Contents", "status": STATUS_OK,
             "explanation": (
                 "Table of Contents present."
                 if has_toc else
                 f"Document is ~{page_count} page(s) with no detected headings – TOC may not be required."
             )}]


# ---------------------------------------------------------------------------
# 12. Acronyms – flag undefined acronyms
# ---------------------------------------------------------------------------

# Acronyms that are universally understood and should not be flagged
_ALLOWED_ACRONYMS = {
    "GSK", "UK", "US", "USA", "EU", "UN", "WHO", "CEO", "CFO", "HR",
    "IT", "R&D", "PDF", "HTML", "URL", "ID", "FAQ", "AI", "API",
}

_ACRONYM_RE = re.compile(r"\b([A-Z]{2,})\b")
_DEFINED_RE = re.compile(r"\b([A-Z][a-z]+(?: [A-Z][a-z]+)+)\s+\(([A-Z]{2,})\)")


def check_acronyms(raw_text: str) -> list[dict]:
    """
    Rule: Avoid acronyms without definition, or jargon people may not recognise.
    Flags acronyms that appear before they are defined (format: Full Name (ACRONYM)).
    """
    if not raw_text.strip():
        return [{"rule": "Acronyms & Jargon", "status": STATUS_OK,
                 "explanation": "No plain text available for acronym analysis."}]

    # Collect all defined acronyms
    defined = {m.group(2) for m in _DEFINED_RE.finditer(raw_text)}
    defined |= _ALLOWED_ACRONYMS

    # Find all acronyms in the text
    all_acronyms = [m.group(1) for m in _ACRONYM_RE.finditer(raw_text)]

    # Find those that are never defined
    undefined = sorted({a for a in all_acronyms if a not in defined})

    if not undefined:
        return [{"rule": "Acronyms & Jargon", "status": STATUS_OK,
                 "explanation": "All acronyms appear to be defined or are commonly known."}]

    return [{"rule": "Acronyms & Jargon", "status": STATUS_WARNING,
             "explanation": (
                 f"Found {len(undefined)} acronym(s) that may not be defined "
                 "or commonly understood:\n"
                 + "  " + ", ".join(undefined[:15])
                 + ("\n  …and more." if len(undefined) > 15 else "")
                 + "\n\nDefine each acronym on first use: Full Name (FN)."
             )}]


# ---------------------------------------------------------------------------
# 13. Inclusive language
# ---------------------------------------------------------------------------

_NON_INCLUSIVE: dict[str, str] = {
    # Gender-exclusive terms
    r"\bguys\b": "everyone / team / folks",
    r"\bmanpower\b": "workforce / staff / personnel",
    r"\bmankind\b": "humanity / humankind / people",
    r"\bmanmade\b": "artificial / manufactured / synthetic",
    r"\bblacklist\b": "blocklist / denylist",
    r"\bwhitelist\b": "allowlist / safelist",
    r"\bchairman\b": "chair / chairperson",
    r"\bstewardess\b": "flight attendant",
    r"\bhostess\b": "host",
    r"\bsalesman\b": "sales representative / sales associate",
    r"\bpoliceman\b": "police officer",
    r"\bfireman\b": "firefighter",
    r"\bhe or she\b": "they",
    r"\bhe\/she\b": "they",
    r"\bhis\/her\b": "their",
    # Ableist / potentially exclusionary
    r"\bcrazy\b": "unexpected / difficult / extreme",
    r"\binsane\b": "extreme / unbelievable",
    r"\blame\b": "blame (consider whether more neutral phrasing applies)",
    r"\bdumb\b": "unclear / confusing",
    r"\bblind spot\b": "gap / oversight",
    # Cultural idioms (may confuse non-native speakers)
    r"\bball park\b": "approximate / rough estimate",
    r"\bballpark\b": "approximate / rough estimate",
    r"\bboil the ocean\b": "do too much",
    r"\bdriving blind\b": "working without information",
    r"\bthrow under the bus\b": "unfairly blame someone",
    r"\bpivot\b": "change direction (if used as pure business jargon)",
}


def check_inclusive_language(raw_text: str) -> list[dict]:
    """
    Rule: Ensure you write using inclusive language, making choices that are
          respectful of people's different backgrounds, cultures and experience.
          Avoid jargon, sayings, idioms, and language people may not recognise.
    """
    if not raw_text.strip():
        return [{"rule": "Inclusive Language", "status": STATUS_OK,
                 "explanation": "No plain text available for inclusive language analysis."}]

    text_lower = raw_text.lower()
    findings: list[str] = []

    for pattern, suggestion in _NON_INCLUSIVE.items():
        if re.search(pattern, text_lower):
            term = pattern.replace(r"\b", "").replace("\\", "")
            findings.append(f'"{term}" → consider: {suggestion}')

    if not findings:
        return [{"rule": "Inclusive Language", "status": STATUS_OK,
                 "explanation": "No obviously non-inclusive or exclusionary language detected."}]

    return [{"rule": "Inclusive Language", "status": STATUS_WARNING,
             "explanation": (
                 f"Found {len(findings)} potentially non-inclusive term(s). "
                 "Review and update where appropriate:\n"
                 + "\n".join(f"  • {f}" for f in findings)
             )}]


# ---------------------------------------------------------------------------
# 14. Low-contrast colour warning
# ---------------------------------------------------------------------------
# Orange #F36633 on white is borderline; flag text using it at small sizes.

_LOW_CONTRAST_COLOURS = {
    "F36633",  # GSK orange
    "FF6600", "FF9900", "FFCC00", "FFD700",  # common yellows/oranges
    "99CC00", "66CC00",  # light greens
    "00CCFF", "33CCFF",  # light blues
}


def check_low_contrast_colour(doc_data: dict) -> list[dict]:
    """
    Rule: When using low-contrast colours (e.g. orange #F36633), use at
          least 12pt text (the guideline explicitly calls this out).
    """
    paragraphs = doc_data.get("paragraphs", [])
    issues: list[str] = []

    for p in paragraphs:
        for run in p["runs"]:
            colour = (run.get("color_rgb") or "").upper()
            size = run.get("font_size_pt")
            text = run["text"].strip()
            if colour in _LOW_CONTRAST_COLOURS and text:
                if size is not None and size < 12:
                    issues.append(
                        f'"{text[:40]}" – colour #{colour} at {size}pt '
                        f"[{p['style']}]"
                    )

    if not issues:
        return [{"rule": "Low-Contrast Colour Size", "status": STATUS_OK,
                 "explanation": "No low-contrast colour text found below 12pt."}]

    return [{"rule": "Low-Contrast Colour Size", "status": STATUS_VIOLATED,
             "explanation": (
                 "Low-contrast colours (e.g. orange) must be used at ≥12pt. "
                 f"Found {len(issues)} instance(s):\n"
                 + "\n".join(f"  • {i}" for i in issues[:5])
             )}]


# ---------------------------------------------------------------------------
# 15. Layout – white space / clutter heuristic
# ---------------------------------------------------------------------------

def check_layout_whitespace(doc_data: dict) -> list[dict]:
    """
    Rule: Keep design layouts uncluttered with plenty of white space.
    Heuristic: flag documents where >85 % of paragraphs are non-empty and
    very long (>150 words), suggesting dense, unbroken blocks of text.
    """
    paragraphs = doc_data.get("paragraphs", [])
    body = _body_paragraphs(paragraphs)
    if not body:
        return [{"rule": "Layout – White Space", "status": STATUS_OK,
                 "explanation": "No body paragraphs to evaluate."}]

    long_paras = [p for p in body if _word_count(p["text"]) > 150]
    ratio = len(long_paras) / len(body)

    if ratio > 0.40:
        return [{"rule": "Layout – White Space", "status": STATUS_WARNING,
                 "explanation": (
                     f"{len(long_paras)} of {len(body)} body paragraphs are very long "
                     "(>150 words). Consider breaking up dense text with subheadings, "
                     "bullet points, or shorter paragraphs to improve readability and "
                     "allow more white space."
                 )}]

    return [{"rule": "Layout – White Space", "status": STATUS_OK,
             "explanation": "Paragraph lengths appear reasonable for an accessible layout."}]


# ---------------------------------------------------------------------------
# 16. Heading hierarchy – headings used at consistent levels
# ---------------------------------------------------------------------------

def check_heading_hierarchy(doc_data: dict) -> list[dict]:
    """
    Rule: Use headings, sub-headings, and body copy consistently at different
          weights and sizes to create a clear structure and hierarchy.
    Flags: heading levels that are skipped (e.g. H1 → H3, no H2).
    """
    paragraphs = doc_data.get("paragraphs", [])
    heading_levels = []
    heading_re = re.compile(r"heading\s+(\d+)", re.IGNORECASE)

    for p in paragraphs:
        m = heading_re.search(p["style"])
        if m:
            heading_levels.append(int(m.group(1)))

    if not heading_levels:
        return [{"rule": "Heading Hierarchy", "status": STATUS_OK,
                 "explanation": "No headings detected – or document uses a flat structure."}]

    issues: list[str] = []
    prev = 0
    for level in heading_levels:
        if level - prev > 1 and prev != 0:
            issues.append(
                f"Heading level jumped from H{prev} to H{level} "
                f"(H{prev + 1} was skipped)"
            )
        prev = level

    if issues:
        return [{"rule": "Heading Hierarchy", "status": STATUS_WARNING,
                 "explanation": (
                     "Skipping heading levels can confuse screen readers. "
                     "Found the following jumps:\n"
                     + "\n".join(f"  • {i}" for i in issues)
                 )}]

    return [{"rule": "Heading Hierarchy", "status": STATUS_OK,
             "explanation": "Heading levels are used in a consistent hierarchy."}]
             
def check_real_heading_styles(doc_data: dict) -> list[dict]:
    """
    Flag paragraphs that appear to be headings (e.g., short, bold, standalone)
    but do not use a proper Heading style.
    Also flag title case in these pseudo‑headings.
    """
    paragraphs = doc_data.get("paragraphs", [])
    violations = []
    warning_details = []

    for p in paragraphs:
        text = p["text"].strip()
        if not text or p["is_heading"] or p["is_title"] or p["is_caption"]:
            continue

        # Heuristic: short line (≤ 60 chars), bold, and not a list item
        if len(text) <= 60 and p["runs"] and any(run["bold"] for run in p["runs"]):
            if not p["is_list"]:
                # This is a fake heading
                violations.append(f'"{text[:50]}" (style: {p["style"]})')

                # Check for title case (every major word capitalised)
                words = text.split()
                if len(words) > 2:
                    common_lower = {'and', 'of', 'the', 'to', 'for', 'with', 'on', 'at', 'by', 'in', 'a', 'an'}
                    title_case_count = sum(1 for w in words if w and w[0].isupper() and w.lower() not in common_lower)
                    if title_case_count > len(words) / 2:
                        warning_details.append(f'"{text[:50]}" – title case (use sentence case)')

    if violations:
        explanation = (
            f"Found {len(violations)} paragraph(s) that look like headings "
            "but are not formatted with a proper Heading style. "
            "Use Heading 1, Heading 2, etc. for accessibility.\n"
            + "\n".join(f"  • {v}" for v in violations[:8])
        )
        if warning_details:
            explanation += "\n\nAdditionally, title case detected in some headings:\n" + "\n".join(f"  • {w}" for w in warning_details[:5])
        return [{"rule": "Real Heading Styles (WCAG 1.3.1)", "status": STATUS_VIOLATED, "explanation": explanation}]

    return [{"rule": "Real Heading Styles", "status": STATUS_OK, "explanation": "All apparent headings use proper heading styles or the document has no headings."}]

# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def run_all_checks(
    raw_text: str = "",
    doc_data: dict | None = None,
) -> list[dict]:
    """
    Run every accessibility and inclusion check.

    Parameters
    ----------
    raw_text  : plain text extracted from the document (used for text-only checks)
    doc_data  : rich formatting dict from extraction.extract_rich_docx_data()
                (required for formatting checks; if None, formatting checks are skipped)

    Returns
    -------
    List of result dicts with keys: rule, status, explanation.
    """
    results: list[dict] = []

    if doc_data:
        results += check_text_alignment(doc_data)
        results += check_heading_formatting(doc_data)
        results += check_real_heading_styles(doc_data)   # if you added this earlier
        results += check_underline_usage(doc_data)
        results += check_sentence_capitalisation(doc_data)
        results += check_font_size(doc_data)
        results += check_font_family(doc_data)
        results += check_bullet_usage(doc_data, raw_text)
        results += check_bold_overuse(doc_data)
        results += check_italics_overuse(doc_data)
        results += check_hyperlink_naming(doc_data)
        results += check_hyperlink_formatting(doc_data)   # <-- ADD THIS LINE
        results += check_table_of_contents(doc_data)
        results += check_low_contrast_colour(doc_data)
        results += check_layout_whitespace(doc_data)
        results += check_heading_hierarchy(doc_data)
    else:
        # Formatting checks unavailable – add informational placeholder
        results.append({
            "rule": "Formatting Checks",
            "status": STATUS_WARNING,
            "explanation": (
                "Rich formatting data is not available (only supported for .docx files). "
                "Checks for font size, alignment, bold/italic overuse, etc. were skipped."
            ),
        })

    # Text-only checks (work on both PDF text and DOCX plain text)
    if raw_text.strip():
        results += check_acronyms(raw_text)
        results += check_inclusive_language(raw_text)
    else:
        results.append({
            "rule": "Text Analysis",
            "status": STATUS_WARNING,
            "explanation": "No plain text was available for acronym and language analysis.",
        })

    return results


# ---------------------------------------------------------------------------
# Backwards-compatibility alias
# ---------------------------------------------------------------------------
# app.py and compliance/__init__.py import check_article_compliance;
# run_all_checks is the canonical name going forward — both work.
check_article_compliance = run_all_checks