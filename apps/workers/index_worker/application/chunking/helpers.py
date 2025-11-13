import hashlib


def deterministic_id(*parts: str) -> str:
    """Build a deterministic identifier by hashing the given string parts."""
    h = hashlib.sha1()
    for p in parts:
        if p is None:
            p = ""
        h.update(p.encode("utf-8"))
        h.update(b"\x00")
    return h.hexdigest()

def normalize_text(src: str) -> str:
    """
    Normalize text for chunking.
    - Converts CRLF/CR to LF, then replaces newlines with spaces.
    - Collapses multiple spaces to a single space and trims.
    """
    # Normalize whitespace/newlines: collapse newlines to spaces and reduce runs of spaces
    s = src.replace("\r\n", "\n").replace("\r", "\n")
    s = s.replace("\n", " ")
    # Collapse multiple spaces to a single space
    return " ".join(s.split()).strip()