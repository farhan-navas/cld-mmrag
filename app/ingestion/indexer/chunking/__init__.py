"""
Chunking strategies for different document types.
"""

from .strategies import route_profile, get_chunker
from .text_splitter import recursive_split_text, create_overlap_chunks, split_fenced_code_blocks
from .pdf_chunker import chunk_blocks
from .excel_chunker import chunk_xlsx
from .pptx_chunker import chunk_pptx

__all__ = [
    "route_profile",
    "get_chunker",
    "recursive_split_text",
    "create_overlap_chunks",
    "split_fenced_code_blocks",
    "chunk_blocks",
    "chunk_xlsx",
    "chunk_pptx",
]
