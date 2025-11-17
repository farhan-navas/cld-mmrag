"""
Indexer package for document processing and chunking.

This package provides a complete document indexing pipeline with support
for multiple file types (PDF, DOCX, PPTX, XLSX, images) and intelligent
chunking strategies.
"""

from .clients import search_client, search_index_client, di_client, aoai_client
from .embeddings import get_embedding, embedding_dimension
from .index_manager import ensure_index
from .uploader import upsert_chunks
from .utils import sha1, stable_id, DATA_DIR, PROJECT_ROOT

# Extractors
from .extractors.document_intelligence import extract_blocks_with_di
from .extractors.excel import extract_excel_sheets
from .extractors.powerpoint import extract_slides

# Chunking
from .chunking.strategies import route_profile, get_chunker
from .chunking.text_splitter import recursive_split_text, create_overlap_chunks, split_fenced_code_blocks
from .chunking.pdf_chunker import chunk_blocks
from .chunking.excel_chunker import chunk_xlsx
from .chunking.pptx_chunker import chunk_pptx

# Main entry point
from .run_indexer import main

__all__ = [
    # Clients
    "search_client",
    "search_index_client",
    "di_client",
    "aoai_client",
    # Embeddings
    "get_embedding",
    "embedding_dimension",
    # Index management
    "ensure_index",
    # Upload
    "upsert_chunks",
    # Utils
    "sha1",
    "stable_id",
    "DATA_DIR",
    "PROJECT_ROOT",
    # Extractors
    "extract_blocks_with_di",
    "extract_excel_sheets",
    "extract_slides",
    # Chunking
    "route_profile",
    "get_chunker",
    "recursive_split_text",
    "create_overlap_chunks",
    "split_fenced_code_blocks",
    "chunk_blocks",
    "chunk_xlsx",
    "chunk_pptx",
    # Main
    "main",
]

