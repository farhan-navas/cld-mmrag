"""
Document extractors for different file types.
"""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Dict, List, Tuple, Callable, Any

from app.config import config

from .document_intelligence import extract_blocks_with_di
from .excel import extract_excel_sheets
from .markitdown import extract_blocks_with_markitdown
from .powerpoint import extract_slides

logger = logging.getLogger("indexer.extractors")

def _extractor_mode() -> str:
    mode = getattr(config.indexing, "block_extractor", "markitdown") or "markitdown"
    mode = mode.lower()
    if mode not in {"di", "markitdown"}:
        logger.warning("Unknown extractor mode '%s'. Falling back to markitdown first.", mode)
        return "markitdown"
    return mode


def _try_extractor(
    fn: Callable[[Path], List[Dict[str, Any]]],
    label: str,
    file_path: Path,
) -> Tuple[bool, List[Dict[str, Any]]]:
    try:
        logger.info("Starting %s extraction for %s", label, file_path.name)
        blocks = fn(file_path)
        if blocks:
            return True, blocks
        logger.warning("%s extractor returned no content for %s", label, file_path.name)
        return False, []
    except Exception as exc:  # pragma: no cover - external service
        logger.warning("%s extractor failed for %s: %s", label, file_path.name, exc)
        return False, []


def extract_blocks(file_path: Path) -> List[Dict[str, Any]]:
    """Route to the configured block extractor with automatic fallback."""
    mode = _extractor_mode()
    primary_label = "Document Intelligence" if mode == "di" else "MarkItDown"
    fallback_label = "MarkItDown" if mode == "di" else "Document Intelligence"
    primary_fn = extract_blocks_with_di if mode == "di" else extract_blocks_with_markitdown
    fallback_fn = extract_blocks_with_markitdown if mode == "di" else extract_blocks_with_di

    ok, blocks = _try_extractor(primary_fn, primary_label, file_path)
    if ok:
        return blocks

    logger.info("Falling back to %s for %s", fallback_label, file_path.name)
    _, fallback_blocks = _try_extractor(fallback_fn, fallback_label, file_path)
    return fallback_blocks

__all__ = [
    "extract_blocks",
    "extract_blocks_with_di",
    "extract_blocks_with_markitdown",
    "extract_excel_sheets",
    "extract_slides",
]
