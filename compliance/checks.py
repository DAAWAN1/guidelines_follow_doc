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
    heading3_used = re.search(r"Heading 3|Heading\s*3", article_text, re.IGNORECASE)
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
        kw_list = []

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

    # =====================================================================
    # NEW CHECKS from provided documents (31-37)
    # =====================================================================

    # ----- 31. Title length -----
    title = None
    title_match = re.search(r'^Title:\s*(.+)', article_text, re.MULTILINE | re.IGNORECASE)
    if title_match:
        title = title_match.group(1).strip()
    if not title:
        for line in article_text.splitlines():
            stripped = line.strip()
            if stripped and not re.match(r'^(SECTION|##|\[\[|\{|\[|\|)', stripped):
                title = stripped
                break
    if title:
        if len(title) <= 120:
            rules.append({"rule": "Article title is within 120 characters", "status": "✅ Followed",
                          "explanation": f"Title length: {len(title)} characters."})
        else:
            rules.append({"rule": "Article title is within 120 characters", "status": "❌ Violated",
                          "explanation": f"Title is {len(title)} characters – exceed maximum of 120."})
    else:
        rules.append({"rule": "Article title is within 120 characters", "status": "⚠️ Undetermined",
                      "explanation": "Could not extract article title."})

    # ----- 32. Content is not in FAQ format -----
    if re.search(r'\b(FAQ|Frequently\s+Asked\s+Questions)\b', article_text, re.IGNORECASE):
        rules.append({"rule": "Content is not in FAQ format", "status": "❌ Violated",
                      "explanation": "Articles should not be in FAQ style. Use structured sections instead."})
    else:
        rules.append({"rule": "Content is not in FAQ format", "status": "✅ Followed",
                      "explanation": "No FAQ pattern detected."})

    # ----- 33. Hyperlink text is descriptive (not a bare URL) -----
    bare_url_found = False
    for line in article_text.splitlines():
        urls = re.findall(r'https?://\S+', line)
        for url in urls:
            remaining = line.replace(url, '', 1).strip()
            if len(remaining) <= 10:
                bare_url_found = True
                break
        if bare_url_found:
            break
    if bare_url_found:
        rules.append({"rule": "Hyperlink text is descriptive (not bare URL)", "status": "❌ Violated",
                      "explanation": "Found at least one hyperlink that is just a raw URL. Use a descriptive link name."})
    else:
        rules.append({"rule": "Hyperlink text is descriptive (not bare URL)", "status": "✅ Followed",
                      "explanation": "No bare URLs detected."})

    # ----- 34. Avoid using accordions for important content -----
    if re.search(r'accordion', article_text, re.IGNORECASE):
        rules.append({"rule": "Avoid using accordions for important content", "status": "⚠️ Warning",
                      "explanation": "Accordions can impair accessibility and printing. Ensure critical info is not collapsed."})
    else:
        rules.append({"rule": "Avoid using accordions for important content", "status": "✅ Followed",
                      "explanation": "No accordions mentioned."})

    # ----- 35. Bullets use standard characters -----
    ACCEPTABLE_BULLETS = {
        '-', '*', '•', '◦', '▪', '▸', '▹', '‣', '⁃', '➢', '–', '—', '▪', '❖', '❑', '❒',
        '✓', '✔'
    }
    non_standard_found = False
    for line in article_text.splitlines():
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r'^(\S)(?:\s)', stripped)
        if m:
            first_char = m.group(1)
            if first_char.isalnum():
                continue
            if first_char not in ACCEPTABLE_BULLETS:
                non_standard_found = True
                break
    if non_standard_found:
        rules.append({"rule": "Bullets use standard characters", "status": "⚠️ Warning",
                      "explanation": "Found non‑standard bullet characters. Use plain dashes or standard bullets."})
    else:
        rules.append({"rule": "Bullets use standard characters", "status": "✅ Followed",
                      "explanation": "Bullets appear standard."})

    # ----- 36. Avoid all‑caps text -----
    all_caps_lines = 0
    for line in article_text.splitlines():
        stripped = line.strip()
        if not stripped or stripped.isdigit():
            continue
        if stripped.isupper() and len(stripped) > 10:
            all_caps_lines += 1
    if all_caps_lines > 3:
        rules.append({"rule": "Avoid all‑caps text", "status": "⚠️ Warning",
                      "explanation": f"Found {all_caps_lines} lines of all‑uppercase text. Use sentence case for readability."})
    else:
        rules.append({"rule": "Avoid all‑caps text", "status": "✅ Followed",
                      "explanation": "No excessive all‑caps text."})

    # ----- 37. Heading nesting: no skipped levels -----
    if heading3_used and not heading2_used:
        rules.append({"rule": "Heading nesting: no skipped levels", "status": "❌ Violated",
                      "explanation": "Heading 3 used without Heading 2. Maintain logical hierarchy."})
    else:
        rules.append({"rule": "Heading nesting: no skipped levels", "status": "✅ Followed",
                      "explanation": "Heading levels appear correctly nested."})

    # =====================================================================
    # ADDITIONAL CHECKS (38-45) based on both documents
    # =====================================================================

    # ----- 38. Keywords contain no country / site names -----
    country_names = {
        'afghanistan', 'albania', 'algeria', 'andorra', 'angola', 'argentina', 'armenia', 'australia',
        'austria', 'azerbaijan', 'bahamas', 'bahrain', 'bangladesh', 'barbados', 'belarus', 'belgium',
        'belize', 'benin', 'bhutan', 'bolivia', 'bosnia', 'botswana', 'brazil', 'brunei', 'bulgaria',
        'burkina faso', 'burundi', 'cambodia', 'cameroon', 'canada', 'cape verde', 'chad', 'chile',
        'china', 'colombia', 'comoros', 'congo', 'costa rica', 'croatia', 'cuba', 'cyprus', 'czechia',
        'denmark', 'djibouti', 'dominica', 'dominican republic', 'ecuador', 'egypt', 'el salvador',
        'equatorial guinea', 'eritrea', 'estonia', 'eswatini', 'ethiopia', 'fiji', 'finland', 'france',
        'gabon', 'gambia', 'georgia', 'germany', 'ghana', 'greece', 'grenada', 'guatemala', 'guinea',
        'guinea-bissau', 'guyana', 'haiti', 'honduras', 'hungary', 'iceland', 'india', 'indonesia',
        'iran', 'iraq', 'ireland', 'israel', 'italy', 'jamaica', 'japan', 'jordan', 'kazakhstan', 'kenya',
        'kiribati', 'korea', 'kosovo', 'kuwait', 'kyrgyzstan', 'laos', 'latvia', 'lebanon', 'lesotho',
        'liberia', 'libya', 'liechtenstein', 'lithuania', 'luxembourg', 'madagascar', 'malawi', 'malaysia',
        'maldives', 'mali', 'malta', 'marshall islands', 'mauritania', 'mauritius', 'mexico', 'micronesia',
        'moldova', 'monaco', 'mongolia', 'montenegro', 'morocco', 'mozambique', 'myanmar', 'namibia',
        'nauru', 'nepal', 'netherlands', 'new zealand', 'nicaragua', 'niger', 'nigeria', 'north macedonia',
        'norway', 'oman', 'pakistan', 'palau', 'palestine', 'panama', 'papua new guinea', 'paraguay',
        'peru', 'philippines', 'poland', 'portugal', 'qatar', 'romania', 'russia', 'rwanda',
        'saint kitts', 'saint lucia', 'saint vincent', 'samoa', 'san marino', 'sao tome', 'saudi arabia',
        'senegal', 'serbia', 'seychelles', 'sierra leone', 'singapore', 'slovakia', 'slovenia',
        'solomon islands', 'somalia', 'south africa', 'south sudan', 'spain', 'sri lanka', 'sudan',
        'suriname', 'sweden', 'switzerland', 'syria', 'taiwan', 'tajikistan', 'tanzania', 'thailand',
        'timor-leste', 'togo', 'tonga', 'trinidad and tobago', 'tunisia', 'turkey', 'turkmenistan',
        'tuvalu', 'uganda', 'ukraine', 'united arab emirates', 'united kingdom', 'usa', 'united states',
        'uruguay', 'uzbekistan', 'vanuatu', 'vatican', 'venezuela', 'vietnam', 'yemen', 'zambia', 'zimbabwe'
    }
    country_in_keywords = False
    if kw_list:
        for kw in kw_list:
            kw_stripped = kw.strip().lower()
            if kw_stripped in country_names:
                country_in_keywords = True
                break
    if country_in_keywords:
        rules.append({"rule": "Keywords: no country/site names", "status": "❌ Violated",
                      "explanation": "One or more keywords are country names. Remove them."})
    else:
        # If no keywords list at all we already reported violation; else it's followed
        if kw_list:
            rules.append({"rule": "Keywords: no country/site names", "status": "✅ Followed",
                          "explanation": "No country names found in keywords."})
        else:
            rules.append({"rule": "Keywords: no country/site names", "status": "⚠️ Undetermined",
                          "explanation": "Keywords section missing or unparseable."})

    # ----- 39. Acronyms defined on first use -----
    # Find potential acronyms (UPPERCASE words of 2+ chars)
    acronym_candidates = re.findall(r'\b([A-Z]{2,}(?:\.[A-Z])?)\b', article_text)  # allows U.S. like?
    acronym_candidates = [a for a in acronym_candidates if len(a) >= 2 and a not in {'US', 'UK', 'EU', 'GSK', 'IT', 'HR', 'AI', 'OK', 'PDF', 'URL'}]
    undefined_acronyms = []
    for acro in acronym_candidates:
        # look for definition pattern: either "acro (definition)" or "definition (acro)"
        # search in surrounding text (simple approach: whole article)
        def_pattern = re.compile(r'\b' + re.escape(acro) + r'\s*\(([^)]+)\)|\(([^)]+)\)\s*' + re.escape(acro), re.IGNORECASE)
        if not def_pattern.search(article_text):
            undefined_acronyms.append(acro)
    if undefined_acronyms:
        rules.append({"rule": "Acronyms are defined on first use", "status": "⚠️ Warning",
                      "explanation": f"Found undefined acronyms: {', '.join(undefined_acronyms[:5])}. Spell out the first time they appear."})
    else:
        rules.append({"rule": "Acronyms are defined on first use", "status": "✅ Followed",
                      "explanation": "All detected acronyms appear to be defined."})

    # ----- 40. Video: Captions provided -----
    if "video" in text_lower:
        if re.search(r'captions?|subtitles?', article_text, re.IGNORECASE):
            rules.append({"rule": "Video captions provided", "status": "✅ Followed",
                          "explanation": "Mentions captions/subtitles for video."})
        else:
            rules.append({"rule": "Video captions provided", "status": "❌ Violated",
                          "explanation": "Video present but no mention of captions."})
    else:
        rules.append({"rule": "Video captions provided", "status": "⚠️ Not applicable",
                      "explanation": "No video mentioned in the article."})

    # ----- 41. Video: Autoplay disabled -----
    if "video" in text_lower:
        if re.search(r'do not autoplay|no autoplay|click to play|manually play', article_text, re.IGNORECASE):
            rules.append({"rule": "Video does not autoplay", "status": "✅ Followed",
                          "explanation": "Autoplay explicitly disabled."})
        else:
            rules.append({"rule": "Video does not autoplay", "status": "❌ Violated",
                          "explanation": "Video should not autoplay; no explicit statement found."})
    else:
        rules.append({"rule": "Video does not autoplay", "status": "⚠️ Not applicable",
                      "explanation": "No video mentioned."})

    # ----- 42. Hashtags use CamelCase (#InitialCaps) -----
    hashtags = re.findall(r'#(\w+)', article_text)
    non_camel = []
    for tag in hashtags:
        # CamelCase means at least one uppercase letter after a lowercase
        if not re.search(r'[a-z][A-Z]', tag) and tag.islower():
            non_camel.append(f'#{tag}')
    if non_camel:
        rules.append({"rule": "Hashtags use CamelCase (#LikeThis)", "status": "❌ Violated",
                      "explanation": f"Non‑CamelCase hashtags: {', '.join(non_camel[:5])}. Capitalize each word."})
    else:
        rules.append({"rule": "Hashtags use CamelCase (#LikeThis)", "status": "✅ Followed",
                      "explanation": "All hashtags are CamelCase or not present."})

    # ----- 43. Links requiring sign‑in include note -----
    # Check if any URL is in the text and the phrase "requires sign in" appears somewhere
    has_url = bool(re.search(r'https?://', article_text))
    has_signin_note = bool(re.search(r'requires sign[-\s]in to access', article_text, re.IGNORECASE))
    if has_url:
        if has_signin_note:
            rules.append({"rule": "Links requiring sign‑in include note", "status": "✅ Followed",
                          "explanation": "Sign‑in disclaimer present near links."})
        else:
            rules.append({"rule": "Links requiring sign‑in include note", "status": "⚠️ Warning",
                          "explanation": "If any link requires sign‑in, add '(requires sign in to access)'."})
    else:
        rules.append({"rule": "Links requiring sign‑in include note", "status": "⚠️ Not applicable",
                      "explanation": "No hyperlinks detected in the article."})

    # ----- 44. Alternative formats statement -----
    if re.search(r'alternative formats?|available on request|accessible formats?', article_text, re.IGNORECASE):
        rules.append({"rule": "Alternative formats offered", "status": "✅ Followed",
                      "explanation": "Statement about alternative formats found."})
    else:
        rules.append({"rule": "Alternative formats offered", "status": "⚠️ Warning",
                      "explanation": "Consider adding a note that alternative formats are available on request."})

    # ----- 45. Body text uses Paragraph style -----
    if re.search(r'Paragraph\s*(style|format)', article_text, re.IGNORECASE):
        rules.append({"rule": "Body text uses Paragraph style", "status": "✅ Followed",
                      "explanation": "Paragraph style mentioned for body text."})
    else:
        rules.append({"rule": "Body text uses Paragraph style", "status": "⚠️ Warning",
                      "explanation": "Not explicitly stated; ensure body text uses the 'Paragraph' style."})

    return rules