"""
STUDIQS® SmartParent™ (v6.3 Complete) - Text Sanitization & OCR Normalization
=============================================================================
Module: src.smartparent.utils.text_cleaner

Provides text normalization, OCR ligature repairs, whitespace compaction,
and language compliance filters (including Tamil exclusion guards).
=============================================================================
"""

import re
import unicodedata
from typing import List, Optional


# Unicode range for Tamil: U+0B80 - U+0BFF
TAMIL_UNICODE_PATTERN = re.compile(r"[\u0B80-\u0BFF]")

# Common OCR typographical misreads & ligatures
OCR_REPLACEMENTS = [
    (r"\bﬁ\b", "fi"),
    (r"\bﬂ\b", "fl"),
    (r"[“”]", '"'),
    (r"[‘’]", "'"),
    (r"[\u2013\u2014]", "-"),
    (r"\s+", " "),
]


def contains_tamil_script(text: str) -> bool:
    """
    Detects whether the provided text contains Tamil Unicode script characters.
    Enforces the strict Tamil language exclusion rule across Classes 1 through 12.
    """
    if not text:
        return False
    return bool(TAMIL_UNICODE_PATTERN.search(text))


def normalize_text_spacing(text: str) -> str:
    """Normalizes whitespace, removes trailing spaces, and standardizes newlines."""
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [line.strip() for line in text.split("\n")]
    # Remove excessive blank lines
    filtered_lines = []
    blank_count = 0
    for line in lines:
        if not line:
            blank_count += 1
            if blank_count <= 1:
                filtered_lines.append("")
        else:
            blank_count = 0
            filtered_lines.append(line)
    return "\n".join(filtered_lines).strip()


def sanitize_question_stem(raw_stem: str) -> str:
    """
    Sanitizes question stem extracted from OCR:
    - Normalizes unicode characters
    - Repairs common OCR ligature artifacts
    - Trims excess whitespace
    """
    if not raw_stem:
        return ""
    stem = unicodedata.normalize("NFKD", raw_stem)
    for pattern, replacement in OCR_REPLACEMENTS:
        stem = re.sub(pattern, replacement, stem)
    return stem.strip()


def extract_keywords_simple(text: str, min_len: int = 3, max_keywords: int = 10) -> List[str]:
    """
    Extracts distinct alphanumeric keywords from text for quick indexing.
    Filters out short words and common English stopwords.
    """
    if not text:
        return []
    words = re.findall(r"\b[a-zA-Z]{" + str(min_len) + r",}\b", text.lower())
    stopwords = {
        "the", "and", "for", "with", "from", "that", "this", "what", "which",
        "where", "when", "how", "why", "are", "was", "were", "been", "have",
        "has", "had", "does", "did", "question", "marks", "find", "solve",
    }
    seen = set()
    result = []
    for w in words:
        if w not in stopwords and w not in seen:
            seen.add(w)
            result.append(w)
            if len(result) >= max_keywords:
                break
    return result

