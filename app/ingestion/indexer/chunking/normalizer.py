"""
Chunk text normalization helpers.

Provides utilities to standardize whitespace and render tabular content
into plain text so search results remain consistent across file types.
"""

from __future__ import annotations

import re
from typing import Sequence, Iterable, List

_SOFT_BREAK_RE = re.compile(r"(?<!\n)\n(?!\n)")
_MULTI_SPACE_RE = re.compile(r"[ \t]+")
_TRAILING_SPACE_BEFORE_NL_RE = re.compile(r"[ \t]+\n")
_LEADING_SPACE_AFTER_NL_RE = re.compile(r"\n[ \t]+")
_MULTIPLE_BLANK_LINES_RE = re.compile(r"\n{3,}")


def _standardize_newlines(text: str) -> str:
    return text.replace("\r\n", "\n").replace("\r", "\n")


def normalize_chunk_text(text: str) -> str:
    """Normalize whitespace for any chunk prior to indexing."""
    cleaned = _standardize_newlines(text)
    cleaned = _TRAILING_SPACE_BEFORE_NL_RE.sub("\n", cleaned)
    cleaned = _LEADING_SPACE_AFTER_NL_RE.sub("\n", cleaned)
    cleaned = _MULTI_SPACE_RE.sub(" ", cleaned)
    cleaned = _MULTIPLE_BLANK_LINES_RE.sub("\n\n", cleaned)
    return cleaned.strip()


def normalize_di_text(text: str) -> str:
    """Collapse soft line breaks that DI emits while keeping paragraphs."""
    cleaned = _standardize_newlines(text)
    cleaned = _SOFT_BREAK_RE.sub(" ", cleaned)
    return normalize_chunk_text(cleaned)


def render_plain_table(rows: Sequence[Sequence[str]]) -> str:
    """Render table rows into a simple pipe-delimited plain-text block."""
    lines: List[str] = []
    for row in rows:
        cells = [str(cell or "").strip() for cell in row]
        line = " | ".join(cells).strip()
        if line:
            lines.append(line)
    return "\n".join(lines)


def dataframe_to_plain_table(df) -> str:
    """Convert a pandas DataFrame into a plain-text table representation."""
    if df.empty:
        return ""
    normalized = df.fillna("").astype(str)
    header = [str(c) for c in normalized.columns]
    body: Iterable[Sequence[str]] = normalized.to_numpy().tolist()
    return render_plain_table([header, *body])
