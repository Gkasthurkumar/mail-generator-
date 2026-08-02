"""
utils.py
--------
Small shared helpers.
"""

import re


def clean_text(text: str) -> str:
    """Remove HTML leftovers, excess whitespace, and non-printable junk
    that commonly comes back from WebBaseLoader / pasted job posts."""
    text = re.sub(r"<[^>]*>", " ", text)          # strip stray HTML tags
    text = re.sub(r"http\S+", " ", text)           # strip raw URLs
    text = re.sub(r"[^a-zA-Z0-9 .,/#+\-\n]", " ", text)  # keep tech-friendly chars
    text = re.sub(r"\s{2,}", " ", text)
    return text.strip()
