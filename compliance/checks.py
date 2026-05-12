import re
from article_cleaner import clean_article_text
from readability import count_sentences

def check_article_compliance(article_text: str, has_images: bool) -> list:
    """
    Run all rule‑based checks against the article text.
    has_images: True if PDF contains at least one embedded image.
    Returns a list of dicts: {rule, status, explanation}
    """
    rules = []
    text_lower = article_text.lower()
    cleaned_text = clean_article_text(article_text)

    # ----- 1. Mandatory feedback callout (QUESTION type) -----
    target_phrase = (
        "Did this article meet your needs? "
        "Click Yes to let us know! If No, please share what's missing so we can improve the content."
    )
    if target_phrase in article_text:
        rules.append({"rule": "Feedback callout (QUESTION type)", "status": "✅ Followed",
                      "explanation": "The mandatory feedback callout phrase is present."})
    else:
        rules.append({"rule": "Feedback callout (QUESTION type)", "status": "❌ Violated",
                      "explanation": "Exact phrase not found. Must appear at end of article."})

    # ----- 2. Table header orange background + bold white text -----
    if re.search(r"orange\s*background.*bold\s*white", article_text, re.IGNORECASE):
        rules.append({"rule": "Table header: orange background + bold white text", "status": "✅ Followed",
                      "explanation": "Matches guideline (#F36633)."})
    elif re.search(r"grey tint|no colour background|dark\s*text", article_text, re.IGNORECASE):
        rules.append({"rule": "Table header: orange background + bold white text", "status": "❌ Violated",
                      "explanation": "Header uses grey/dark text, not orange background."})
    else:
        rules.append({"rule": "Table header: orange background + bold white text", "status": "⚠️ Undetermined",
                      "explanation": "Could not verify header styling."})

    # ----- 3. HEADING LEVELS -----
    heading2_used = re.search(r"Heading 2|Heading\s*2", article_text, re.IGNORECASE)
    heading1_used = re.search(r"Heading 1|Heading\s*1", article_text, re.IGNORECASE)
    if heading2_used and not heading1_used:
        rules.append({"rule": "Heading levels: Heading 2 is default", "status": "✅ Followed",
                      "explanation": "Article uses Heading 2 as main level (no Heading 1)."})
    elif heading1_used and not heading2_used:
        rules.append({"rule": "Heading levels: Heading 2 is default", "status": "❌ Violated",
                      "explanation": "Heading 1 is used but Heading 2 is missing. Use Heading 2 for main sections."})
    elif heading1_used and heading2_used:
        rules.append({"rule": "Heading levels: Heading 2 is default", "status": "⚠️ Warning",
                      "explanation": "Both Heading 1 and Heading 2 present. Ensure Heading 1 is only for very large sections."})
    else:
        rules.append({"rule": "Heading levels: Heading 2 is default", "status": "⚠️ Undetermined",
                      "explanation": "No heading level mentioned in article text."})

    # Avoid generic headings
    if re.search(r"Heading.*?Introduction|^Introduction$", article_text, re.MULTILINE):
        rules.append({"rule": "Headings are descriptive (avoid 'Introduction')", "status": "❌ Violated",
                      "explanation": "Found generic heading 'Introduction'. Use specific titles like 'What is X?'"})
    else:
        rules.append({"rule": "Headings are descriptive (avoid 'Introduction')", "status": "✅ Followed",
                      "explanation": "No generic headings detected."})

    # No numbers in headings
    if re.search(r"^\d+\.\s+\w+", article_text, re.MULTILINE):
        rules.append({"rule": "Headings have no numbers", "status": "❌ Violated",
                      "explanation": "Numbered headings found (e.g., '1. Section'). Remove numbers."})
    else:
        rules.append({"rule": "Headings have no numbers", "status": "✅ Followed",
                      "explanation": "No numbered headings."})

    # ----- 4. Description section -----
    if re.search(r"Description.*?\n", article_text) and "This Knowledge Article" in article_text:
        rules.append({"rule": "Article contains a Description section", "status": "✅ Followed",
                      "explanation": "Starts with 'This Knowledge Article...'"})
    else:
        rules.append({"rule": "Article contains a Description section", "status": "❌ Violated",
                      "explanation": "Missing Description section."})

    # ----- 5. Audience section -----
    if re.search(r"\bAudience\s*[:|]?\b", article_text, re.IGNORECASE):
        rules.append({"rule": "Audience section present", "status": "✅ Followed",
                      "explanation": "Clearly states intended audience."})
    else:
        rules.append({"rule": "Audience section present", "status": "❌ Violated",
                      "explanation": "Every article must define its audience."})

    # ----- 6. Prerequisites / "Access to" -----
    if re.search(r"Prerequisites?\s*[:|]?|\bAccess to\b", article_text, re.IGNORECASE):
        rules.append({"rule": "Prerequisites / 'Access to' section", "status": "✅ Followed",
                      "explanation": "Lists required access or prep."})
    else:
        rules.append({"rule": "Prerequisites / 'Access to' section", "status": "⚠️ Warning",
                      "explanation": "Not explicitly mentioned. Recommended for instructional articles."})

    # ----- 7. Instructions use numbered list -----
    if re.search(r"\d+\.\s+\w+", article_text) and "numbered list" in text_lower:
        rules.append({"rule": "Instructions use numbered list", "status": "✅ Followed",
                      "explanation": "Numbered steps detected."})
    elif re.search(r"\d+\.\s+\w+", article_text):
        rules.append({"rule": "Instructions use numbered list", "status": "✅ Followed",
                      "explanation": "Numbered steps present."})
    else:
        rules.append({"rule": "Instructions use numbered list", "status": "⚠️ Undetermined",
                      "explanation": "No numbered steps found; if tutorial, use numbered list."})

    # ----- 8. Contacts for Further Help -----
    if re.search(r"Contacts? for Further Help", article_text, re.IGNORECASE):
        rules.append({"rule": "Contacts for Further Help section", "status": "✅ Followed", "explanation": "Present."})
    else:
        rules.append({"rule": "Contacts for Further Help section", "status": "❌ Violated",
                      "explanation": "Mandatory section missing."})

    # ----- 9. Keywords -----
    keywords_match = re.search(r"Keywords\s*[:|]\s*([^;]+(?:;\s*[^;]+)+)", article_text, re.IGNORECASE)
    if keywords_match:
        kw_text = keywords_match.group(1)
        kw_list = re.split(r';\s*', kw_text)
        if len(kw_list) >= 30:
            rules.append({"rule": "Keywords (30 semicolon‑separated)", "status": "✅ Followed",
                          "explanation": f"Found {len(kw_list)} keywords."})
        else:
            rules.append({"rule": "Keywords (30 semicolon‑separated)", "status": "❌ Violated",
                          "explanation": f"Only {len(kw_list)} keywords, need 30."})
    else:
        rules.append({"rule": "Keywords (30 semicolon‑separated)", "status": "❌ Violated",
                      "explanation": "No Keywords section found."})

    # ----- 10. Hyperlinks blue & underlined -----
    if "blue" in text_lower and "underline" in text_lower:
        rules.append({"rule": "Hyperlinks are blue and underlined", "status": "✅ Followed",
                      "explanation": "Matches system default."})
    else:
        rules.append({"rule": "Hyperlinks are blue and underlined", "status": "⚠️ Undetermined",
                      "explanation": "Not explicitly stated."})

    # ----- 11. Copy Link button -----
    if "Copy Link" in article_text:
        rules.append({"rule": "Copy Link button visible", "status": "✅ Followed", "explanation": "Mentioned."})
    else:
        rules.append({"rule": "Copy Link button visible", "status": "❌ Violated",
                      "explanation": "Must instruct to use Copy Link button."})

    # ----- 12. Table cell text uses Paragraph style -----
    if re.search(r"Paragraph.*style.*table|table.*Paragraph.*style", article_text, re.IGNORECASE):
        rules.append({"rule": "Table cell text uses Paragraph style", "status": "✅ Followed",
                      "explanation": "Not Heading."})
    else:
        rules.append({"rule": "Table cell text uses Paragraph style", "status": "⚠️ Warning",
                      "explanation": "Not clearly described; ensure table cells use Paragraph."})

    # ----- 13. Table: no copying from external sources -----
    if re.search(r"do not copy a table|paste as plain text|clear formatting", article_text, re.IGNORECASE):
        rules.append({"rule": "Table not copied from external sources", "status": "✅ Followed",
                      "explanation": "Guideline followed."})
    else:
        rules.append({"rule": "Table not copied from external sources", "status": "⚠️ Warning",
                      "explanation": "No mention of avoiding paste from Word/PDF."})

    # ----- 14. Table not imported as image -----
    if re.search(r"do not import.*table.*image", article_text, re.IGNORECASE):
        rules.append({"rule": "Table not imported as image", "status": "✅ Followed",
                      "explanation": "Explicitly avoided."})
    else:
        rules.append({"rule": "Table not imported as image", "status": "⚠️ Warning",
                      "explanation": "No statement; ensure table is real HTML table."})

    # ----- 15. Table Type 2: alternating row background -----
    if re.search(r"alternating.*row|#FAE2D5|light orange.*background", article_text, re.IGNORECASE):
        rules.append({"rule": "Table Type 2: alternating row background (#FAE2D5)", "status": "✅ Followed",
                      "explanation": "Alternating rows used."})
    else:
        rules.append({"rule": "Table Type 2: alternating row background (#FAE2D5)", "status": "⚠️ Undetermined",
                      "explanation": "Not described; only needed if using comparative tables."})

    # ----- 16. Table border colour -----
    if re.search(r"#F1A983|border.*light orange", article_text, re.IGNORECASE):
        rules.append({"rule": "Table Type 2 border colour (#F1A983)", "status": "✅ Followed",
                      "explanation": "Correct border colour."})
    else:
        rules.append({"rule": "Table Type 2 border colour (#F1A983)", "status": "⚠️ Undetermined",
                      "explanation": "Not specified."})

    # ----- 17. Screenshot max width -----
    if has_images:
        if re.search(r"width.*850|max.*850px", article_text, re.IGNORECASE):
            rules.append({"rule": "Screenshot max width 850px", "status": "✅ Followed",
                          "explanation": "Width specified or implied."})
        else:
            rules.append({"rule": "Screenshot max width 850px", "status": "⚠️ Warning",
                          "explanation": "Not mentioned; ensure images are ≤850px wide."})
    else:
        rules.append({"rule": "Screenshot max width 850px", "status": "⚠️ Not applicable",
                      "explanation": "No embedded images detected in PDF."})

    # ----- 18. Screenshots have alt text -----
    if has_images:
        if re.search(r"Alternative description|alt text", article_text, re.IGNORECASE):
            rules.append({"rule": "Screenshots have alt text", "status": "✅ Followed",
                          "explanation": "Alt text described."})
        else:
            rules.append({"rule": "Screenshots have alt text", "status": "❌ Violated",
                          "explanation": "Every image must have alt text."})
    else:
        rules.append({"rule": "Screenshots have alt text", "status": "⚠️ Not applicable",
                      "explanation": "No embedded images detected."})

    # ----- 19. Screenshot annotations use GSK orange -----
    if has_images:
        if re.search(r"#f36633|orange.*annotation|GSK orange", article_text, re.IGNORECASE):
            rules.append({"rule": "Screenshot annotations use GSK orange", "status": "✅ Followed",
                          "explanation": "Matches brand colour."})
        else:
            rules.append({"rule": "Screenshot annotations use GSK orange", "status": "⚠️ Warning",
                          "explanation": "No mention of annotation colour; use #f36633."})
    else:
        rules.append({"rule": "Screenshot annotations use GSK orange", "status": "⚠️ Not applicable",
                      "explanation": "No embedded images detected."})

    # ----- 20. Critical info not only in images -----
    if re.search(r"text version|summary.*below|accessible to screen readers", article_text, re.IGNORECASE):
        rules.append({"rule": "Critical info not only in images", "status": "✅ Followed",
                      "explanation": "Provides text alternative."})
    else:
        rules.append({"rule": "Critical info not only in images", "status": "⚠️ Warning",
                      "explanation": "No text alternative mentioned; ensure critical data is also in text."})

    # ----- 21. Note formatting -----
    note_format = re.search(r"Note:\s*\*\*?|bold.*Note:|Note:.*bold", article_text, re.IGNORECASE)
    if note_format:
        rules.append({"rule": "Note formatting: bold 'Note:' + Paragraph", "status": "✅ Followed",
                      "explanation": "Correctly formatted."})
    else:
        rules.append({"rule": "Note formatting: bold 'Note:' + Paragraph", "status": "⚠️ Warning",
                      "explanation": "Notes should have 'Note:' in bold, rest normal."})

    # ----- 22. Attachment names contain no dates -----
    if re.search(r"\b(19|20)\d{2}\b", article_text) and "attachment" in text_lower:
        rules.append({"rule": "Attachment names contain no dates", "status": "❌ Violated",
                      "explanation": "Found year number in attachment description."})
    else:
        rules.append({"rule": "Attachment names contain no dates", "status": "✅ Followed",
                      "explanation": "No dates detected in attachment names."})

    # ----- 23. Attachment name matches link text -----
    if re.search(r"identical name|same name.*attachment.*link", article_text, re.IGNORECASE):
        rules.append({"rule": "Attachment name matches link text", "status": "✅ Followed",
                      "explanation": "Consistency mentioned."})
    else:
        rules.append({"rule": "Attachment name matches link text", "status": "⚠️ Warning",
                      "explanation": "Ensure the linked text and file name are identical."})

    # ----- 24. Attachments are supplementary -----
    if re.search(r"must not serve as the primary source|complement the main content", article_text, re.IGNORECASE):
        rules.append({"rule": "Attachments are supplementary, not primary", "status": "✅ Followed",
                      "explanation": "Guideline followed."})
    else:
        rules.append({"rule": "Attachments are supplementary, not primary", "status": "⚠️ Warning",
                      "explanation": "No statement; ensure article is self‑contained."})

    # ----- 25. Plain language: short sentences -----
    if cleaned_text:
        sentence_count = count_sentences(cleaned_text)
        total_words = len(cleaned_text.split())
        if sentence_count > 0:
            avg_len = total_words / sentence_count
            if avg_len < 20:
                rules.append({"rule": "Plain language: short sentences (average <20 words)", "status": "✅ Followed",
                              "explanation": f"Average sentence length {avg_len:.1f} words (based on extracted article content)."})
            else:
                rules.append({"rule": "Plain language: short sentences (average <20 words)", "status": "❌ Violated",
                              "explanation": f"Average {avg_len:.1f} words – too long (based on extracted article content)."})
        else:
            rules.append({"rule": "Plain language: short sentences", "status": "⚠️ Undetermined",
                          "explanation": "Could not compute sentence count from article content."})
    else:
        rules.append({"rule": "Plain language: short sentences", "status": "⚠️ Undetermined",
                      "explanation": "No clean article content found for readability analysis."})

    # ----- 26. Active voice -----
    if cleaned_text:
        passive_patterns = r"\b(am|are|is|was|were|be|been|being)\s+(\w+ed|\w+en)\b"
        passive_matches = len(re.findall(passive_patterns, cleaned_text, re.IGNORECASE))
        if passive_matches < 5:
            rules.append({"rule": "Plain language: active voice preferred", "status": "✅ Followed",
                          "explanation": f"Only {passive_matches} passive constructions in article content."})
        else:
            rules.append({"rule": "Plain language: active voice preferred", "status": "⚠️ Warning",
                          "explanation": f"{passive_matches} passive phrases found; rewrite to active where possible."})
    else:
        rules.append({"rule": "Plain language: active voice preferred", "status": "⚠️ Undetermined",
                      "explanation": "No clean article content available."})

    # ----- 27. Spacing -----
    if re.search(r"(Heading 2|^#+\s+.*)\n\s*\n\s*\w", article_text, re.MULTILINE):
        rules.append({"rule": "Spacing: no blank line after heading", "status": "❌ Violated",
                      "explanation": "Blank line found after heading – should be no gap."})
    else:
        rules.append({"rule": "Spacing: no blank line after heading", "status": "✅ Followed",
                      "explanation": "No incorrect spacing detected."})

    if re.search(r"Section.*?\n\s*\n.*?Section", article_text, re.DOTALL | re.IGNORECASE):
        rules.append({"rule": "Spacing: one blank line between sections", "status": "✅ Followed",
                      "explanation": "Sections separated by blank line."})
    else:
        rules.append({"rule": "Spacing: one blank line between sections", "status": "⚠️ Warning",
                      "explanation": "Not clearly separated; use one line of space."})

    # ----- 28. AQI checklist -----
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

    # ----- 29. Missing Information section -----
    if re.search(r"Missing Information", article_text):
        rules.append({"rule": "Missing Information section present (if outdated content)", "status": "✅ Followed",
                      "explanation": "Has a section for outdated info."})
    else:
        rules.append({"rule": "Missing Information section present (if outdated content)", "status": "⚠️ Undetermined",
                      "explanation": "Not needed if all information is up to date."})

    # ----- 30. Callout line breaks use Shift+Enter -----
    if re.search(r"Shift\s*\+\s*Enter", article_text):
        rules.append({"rule": "Callout line breaks use Shift+Enter", "status": "✅ Followed",
                      "explanation": "Correct line break method."})
    else:
        rules.append({"rule": "Callout line breaks use Shift+Enter", "status": "⚠️ Info",
                      "explanation": "Not mentioned; use Shift+Enter to add new lines inside callouts."})

    return rules