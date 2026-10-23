import re
import unicodedata

def normalize_text(text: str) -> str:
    """
    Standardize text from PDF extraction:
    - Normalizes Unicode ligatures (e.g. \ufb00 'ff', \ufb01 'fi', \ufb02 'fl') via NFKD
    - Normalizes typographic quotes, apostrophes, and dashes
    - Removes non-breaking spaces and unusual whitespace
    - Normalizes line breaks
    """
    if not text:
        return ""
    
    # Unicode NFKD normalization decomposes ligatures into base ASCII chars
    text = unicodedata.normalize("NFKD", text)
    
    # Replace common typographic dashes and quotes with standard ASCII
    replacements = {
        "\u2010": "-",  # Hyphen
        "\u2011": "-",  # Non-breaking hyphen
        "\u2012": "-",  # Figure dash
        "\u2013": "-",  # En dash
        "\u2014": "-",  # Em dash
        "\u2015": "-",  # Horizontal bar
        "\u2018": "'",  # Left single quotation mark
        "\u2019": "'",  # Right single quotation mark
        "\u201c": '"',  # Left double quotation mark
        "\u201d": '"',  # Right double quotation mark
        "\u00a0": " ",  # Non-breaking space
        "\u202f": " ",  # Narrow no-break space
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
        
    # Strip carriage returns and standardize spaces
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    # Replace multiple horizontal spaces with a single space
    text = re.sub(r"[ \t]+", " ", text)
    # Strip leading/trailing whitespace per line
    lines = [line.strip() for line in text.split("\n")]
    # Remove consecutive empty lines
    cleaned_lines = []
    prev_empty = False
    for line in lines:
        if not line:
            if not prev_empty:
                cleaned_lines.append("")
                prev_empty = True
        else:
            cleaned_lines.append(line)
            prev_empty = False
            
    return "\n".join(cleaned_lines).strip()

def canonical_content_for_hash(heading: str, body_text: str) -> str:
    """
    Produce a canonical string for SHA-256 calculation.
    Ensures that trivial whitespace variations do not invalidate hashes,
    while meaningful semantic differences alter the hash.
    """
    norm_heading = normalize_text(heading).lower()
    norm_body = normalize_text(body_text)
    # Collapse all whitespace into single spaces for hash comparison
    collapsed_body = re.sub(r"\s+", " ", norm_body).strip()
    return f"{norm_heading}\n{collapsed_body}"

def slugify(text: str) -> str:
    """
    Generate a clean URL/ID friendly slug from text.
    """
    text = normalize_text(text).lower()
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[\s_-]+", "_", text)
    return text.strip("_")
