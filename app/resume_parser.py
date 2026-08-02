"""
resume_parser.py
-----------------
Utility for extracting plain text from an uploaded PDF resume so it can be
fed into the LLM chains for match-scoring and email personalization.
"""

from io import BytesIO
from pypdf import PdfReader


def extract_text_from_pdf(uploaded_file) -> str:
    """
    Extract text from a PDF file.

    Parameters
    ----------
    uploaded_file : UploadedFile | BytesIO | str
        A Streamlit UploadedFile object, a BytesIO buffer, or a filesystem path.

    Returns
    -------
    str
        The concatenated, whitespace-cleaned text of every page in the PDF.
    """
    if hasattr(uploaded_file, "read"):
        # Streamlit's UploadedFile / any file-like object
        data = uploaded_file.read()
        reader = PdfReader(BytesIO(data))
    else:
        # Assume it's a path
        reader = PdfReader(uploaded_file)

    text_parts = []
    for page in reader.pages:
        page_text = page.extract_text() or ""
        text_parts.append(page_text)

    full_text = "\n".join(text_parts)
    return _clean_text(full_text)


def _clean_text(text: str) -> str:
    """Collapse excess whitespace/blank lines produced by PDF extraction."""
    lines = [line.strip() for line in text.splitlines()]
    lines = [line for line in lines if line]
    return "\n".join(lines)
