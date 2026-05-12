import re

def count_sentences(text: str) -> int:
    """
    Count sentences using a robust approach.
    Avoids splitting on common abbreviations.
    """
    abbrev = re.compile(r'\b(?:e\.g|i\.e|vs\.|etc\.|Mr\.|Ms\.|Dr\.|Prof\.|Ltd\.|Inc\.|Corp\.)\b', re.IGNORECASE)
    text = abbrev.sub(lambda m: m.group(0).replace('.', '@@@'), text)
    sentences = re.split(r'[.!?]\s+', text)
    sentences = [s.replace('@@@', '.') for s in sentences]
    sentences = [s for s in sentences if s.strip()]
    return len(sentences)