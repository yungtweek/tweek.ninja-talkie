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
        # Remove Markdown syntax and artifacts
        content = re.sub(r'!\[.*?]\(.*?\)', '', content)
        content = re.sub(r'\[.*?]\(.*?\)', '', content)
        content = re.sub(r'[`*_>#-]', '', content)
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

    # Collapse multiple spaces and newlines
    text = re.sub(r"\n{2,}", "\n", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()