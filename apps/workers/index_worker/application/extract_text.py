"""
Text extraction and cleaning utilities for the indexing worker.
- Supports PDF, TXT, and Markdown files.
- Returns normalized plain text suitable for chunking and embedding.
"""

from io import BytesIO

from pypdf import PdfReader
import re


def extract_text(raw_bytes: bytes, filename: str) -> str:
    """
    Extract plain text from various file formats.

    Parameters:
    - raw_bytes: Raw file bytes.
    - filename: Original filename (used to detect file type).

    Returns:
    - Extracted UTF-8 text string.

    Raises:
    - ValueError: If file format is unsupported.
    """
    if filename.endswith(".pdf"):
        reader = PdfReader(BytesIO(raw_bytes))
        return "\n".join((page.extract_text() or "") for page in reader.pages)

    elif filename.endswith(".txt"):
        return raw_bytes.decode("utf-8", errors="ignore")

    elif filename.endswith(".md"):
        content = raw_bytes.decode("utf-8", errors="ignore")
        # --- Keep markdown extraction lightweight ---
        # Only strip clearly non-semantic blocks here and let the chunker
        # handle structural semantics (headers, lists, etc.).
        # 2) Remove HTML comments
        content = re.sub(r"<!--.*?-->", "", content, flags=re.DOTALL)
        # (Headings like `#`, `##` and list markers `-`, `*` etc. are preserved
        #  so that downstream Markdown-aware chunkers can use them.)
        return content.strip()

    else:
        raise ValueError("Unsupported file format")




def clean_text(text: str) -> str:
    """
    Clean and normalize extracted text.
    - Removes control tokens and invisible characters.
    - Normalizes punctuation, whitespace, and newlines.
    """
    # Remove special control tokens
    text = re.sub(r"<EOS>|<PAD>|<pad>", "", text)

    # Normalize Unicode punctuation and special symbols
    # Normalize quotation marks
    text = re.sub(r"[“”‘’]", '"', text)  # Normalize quotation marks
    # Normalize dashes
    text = re.sub(r"[–—]", "-", text)    # Normalize dashes
    # Remove zero-width spaces
    text = text.replace("\u200b", "")    # Remove zero-width spaces
    # Normalize newline characters
    text = re.sub(r"\r\n|\r", "\n", text)  # Normalize newline characters

    # --- Preserve structural newlines but clean intra-line whitespace ---
    # Split into lines, trim extra spaces/tabs per line
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]

    # Collapse 3+ consecutive blank lines down to at most 2
    normalized_lines = []
    blank_count = 0
    for line in lines:
        if line == "":
            blank_count += 1
            if blank_count > 2:
                continue
        else:
            blank_count = 0
        normalized_lines.append(line)

    text = "\n".join(normalized_lines)

    return text.strip()