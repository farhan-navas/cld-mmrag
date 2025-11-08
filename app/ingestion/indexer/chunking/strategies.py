"""
Chunking strategy router.

This module determines which chunking strategy to use based on file type.
"""

import logging
from pathlib import Path
from typing import Callable, List, Dict, Any

logger = logging.getLogger("indexer.chunking.strategies")


def route_profile(path: Path) -> str:
    """
    Determine chunking strategy based on file type.
    
    :param path: Path to the file
    :return: Profile name: "pptx", "xlsx", "image", or "pdf_like"
    """
    ext = path.suffix.lower()
    if ext in {".pptx"}:
        return "pptx"
    if ext in {".xlsx", ".csv"}:
        return "xlsx"
    if ext in {".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp"}:
        return "image"   # still handled via DI (prebuilt-layout)
    if ext in {".pdf", ".docx"}:
        return "pdf_like"  # current DI path
    return "pdf_like"


def get_chunker(profile: str) -> Callable:
    """
    Get the appropriate chunking function for a given profile.
    
    :param profile: Profile name from route_profile()
    :return: Chunking function
    """
    from app.ingestion.indexer.chunking.pdf_chunker import chunk_blocks
    from app.ingestion.indexer.chunking.excel_chunker import chunk_xlsx
    from app.ingestion.indexer.chunking.pptx_chunker import chunk_pptx
    
    if profile == "xlsx":
        return chunk_xlsx
    elif profile == "pptx":
        return chunk_pptx
    else:
        # pdf_like and image both use DI extraction + block chunking
        return chunk_blocks
