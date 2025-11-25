"""
MarkItDown-based document extractor.

Provides a lightweight alternative to Azure Document Intelligence by
leveraging the open-source MarkItDown converter to obtain markdown and
then normalizes it into the same block schema expected by the chunkers.
"""

from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any, Dict, List

from markitdown import MarkItDown

from app.ingestion.indexer.chunking.normalizer import normalize_di_text, render_plain_table

logger = logging.getLogger("indexer.extractors.markitdown")

_MARKITDOWN_CLIENT: MarkItDown | None = None
_CODE_FENCE_RE = re.compile(r"^(?P<fence>```|~~~)(?P<lang>.*)$")
_HEADING_RE = re.compile(r"^(?P<prefix>#{1,6})\s+(?P<body>.+)$")

def _get_client() -> MarkItDown:
    global _MARKITDOWN_CLIENT
    if _MARKITDOWN_CLIENT is None:
        _MARKITDOWN_CLIENT = MarkItDown()
    return _MARKITDOWN_CLIENT


def _flush_paragraph(buffer: List[str], blocks: List[Dict[str, Any]]) -> None:
    if not buffer:
        return
    text = normalize_di_text("\n".join(buffer))
    buffer.clear()
    if text:
        blocks.append({
            "type": "paragraph",
            "text": text,
            "page": 1,
            "bbox": None,
        })


def _parse_table_line(line: str) -> List[str]:
    trimmed = line.strip().strip("|")
    cells = [cell.strip() for cell in trimmed.split("|")]
    return cells


def _is_separator_row(cells: List[str]) -> bool:
    if not cells:
        return True
    normalized = "".join(cell.replace(":", "").replace("-", "") for cell in cells)
    return normalized.strip() == ""


def _collect_table(lines: List[str], start: int) -> tuple[List[List[str]], int]:
    rows: List[List[str]] = []
    i = start
    while i < len(lines):
        stripped = lines[i].strip()
        if not stripped or not stripped.startswith("|"):
            break
        row = _parse_table_line(lines[i])
        if not _is_separator_row(row):
            rows.append(row)
        i += 1
    return rows, i


def _append_table(blocks: List[Dict[str, Any]], rows: List[List[str]]) -> None:
    if not rows:
        return
    plain = render_plain_table(rows)
    text = normalize_di_text(plain)
    if not text:
        return
    blocks.append({
        "type": "table",
        "text": text,
        "page": 1,
        "bbox": None,
    })


def _parse_markdown(markdown: str) -> List[Dict[str, Any]]:
    blocks: List[Dict[str, Any]] = []
    lines = markdown.splitlines()
    paragraph_buffer: List[str] = []
    i = 0
    total = len(lines)

    while i < total:
        raw_line = lines[i]
        stripped = raw_line.strip()

        if not stripped:
            _flush_paragraph(paragraph_buffer, blocks)
            i += 1
            continue

        fence_match = _CODE_FENCE_RE.match(stripped)
        if fence_match:
            _flush_paragraph(paragraph_buffer, blocks)
            fence = fence_match.group("fence")
            lang = (fence_match.group("lang") or "").strip()
            code_lines: List[str] = []
            i += 1
            while i < total and not lines[i].strip().startswith(fence):
                code_lines.append(lines[i])
                i += 1
            # Skip closing fence if present
            if i < total:
                i += 1
            body = "\n".join(code_lines).strip("\n")
            code_md = f"```{lang}\n{body}\n```".strip()
            if code_md:
                blocks.append({
                    "type": "codeblock",
                    "text": code_md,
                    "page": 1,
                    "bbox": None,
                })
            continue

        heading_match = _HEADING_RE.match(stripped)
        if heading_match:
            _flush_paragraph(paragraph_buffer, blocks)
            heading_text = normalize_di_text(heading_match.group("body"))
            if heading_text:
                blocks.append({
                    "type": "heading",
                    "text": heading_text,
                    "page": 1,
                    "bbox": None,
                })
            i += 1
            continue

        if stripped.startswith("|"):
            rows, next_index = _collect_table(lines, i)
            if rows:
                _flush_paragraph(paragraph_buffer, blocks)
                _append_table(blocks, rows)
                i = next_index
                continue

        paragraph_buffer.append(raw_line)
        i += 1

    _flush_paragraph(paragraph_buffer, blocks)
    return blocks


def extract_blocks_with_markitdown(file_path: Path) -> List[Dict[str, Any]]:
    """Extract normalized blocks from a document using MarkItDown."""
    client = _get_client()
    logger.info("Extracting blocks with markitdown")
    try:
        result = client.convert(file_path)
    except Exception as exc:  # pragma: no cover - relies on external lib
        logger.error("MarkItDown conversion failed for %s: %s", file_path, exc)
        raise

    markdown = getattr(result, "markdown", None) or str(result)
    blocks = _parse_markdown(markdown)
    logger.info("[MarkItDown] Extracted %s blocks from %s", len(blocks), file_path.name)
    return blocks