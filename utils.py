import re

def shorten_filename(filename: str, first=5, last=7) -> str:
    """
    Return a shortened display name without the .pdf extension.
    """
    name = re.sub(r"\.pdf$", "", filename, flags=re.IGNORECASE)
    if len(name) <= 9:
        return name
    return f"{name[:first]}...{name[-last:]}"