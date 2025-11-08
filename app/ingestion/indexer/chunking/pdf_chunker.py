"""
PDF/DOCX semantic chunking strategy.

This module handles chunking of Document Intelligence-extracted blocks
with intelligent handling of headings, tables, code blocks, and paragraphs.
"""

import logging
from typing import List, Dict, Any

from app.config import config
from app.ingestion.indexer.chunking.text_splitter import recursive_split_text, create_overlap_chunks

logger = logging.getLogger("indexer.chunking.pdf")


def chunk_blocks(blocks: List[Dict[str, Any]], title: str, filepath: str) -> List[Dict[str, Any]]:
    """
    Chunk blocks using recursive splitting strategy.
    
    Strategy:
    - Headings: Create section boundaries and hierarchy
    - Tables: Keep as standalone chunks (atomic units)
    - Paragraphs: Use recursive splitting to maintain semantic coherence
    - Code blocks, figures, formulas: Keep atomic
    
    :param blocks: List of block dictionaries from DI extraction
    :param title: Document title
    :param filepath: Document filepath for metadata
    :return: List of chunk dictionaries ready for embedding
    """
    max_chars = config.indexing.chunk_max_chars
    overlap = config.indexing.chunk_overlap_chars
    
    chunks = []
    section_path = []
    
    # Group consecutive paragraphs between headings/tables
    paragraph_buffer = []
    current_page = 1
    
    def flush_paragraphs():
        """Process accumulated paragraphs with recursive chunking."""
        nonlocal paragraph_buffer
        
        if not paragraph_buffer:
            return
        
        # Combine paragraphs with double newlines
        combined_text = "\n\n".join(p["text"] for p in paragraph_buffer)
        
        # Use recursive splitting once
        text_chunks = recursive_split_text(combined_text, max_chars)
        
        # Add overlap between chunks (only for paragraphs)
        if overlap > 0:
            text_chunks = create_overlap_chunks(text_chunks, overlap)
        
        # Create chunk records; use the page of the first paragraph in the buffer
        page = paragraph_buffer[0]["page"]
        for chunk_text in text_chunks:
            if chunk_text.strip():
                chunks.append({
                    "title": title,
                    "filepath": filepath,
                    "page": page,
                    "section_path": " > ".join(section_path[-3:]),
                    "content": chunk_text,
                    "content_markdown": chunk_text,  # already Markdown
                    "bbox": None
                })
        
        paragraph_buffer = []
    
    # Process blocks
    for block in blocks:
        block_type = block["type"]
        text = (block.get("text") or "").strip()
        
        if not text:
            continue
        
        current_page = block.get("page", current_page)
        if block_type == "heading":
            # Flush any pending paragraphs
            flush_paragraphs()
            
            # Update section hierarchy
            section_path.append(text[:120])
            if len(section_path) > 8:
                section_path = section_path[-8:]
            
            continue
        
        elif block_type == "table":
            # Flush pending paragraphs first
            flush_paragraphs()
            
            # Tables are kept as standalone chunks
            table_text = text
            table_md = block.get("markdown", text)
            
            # If table is too large, split it by rows
            if len(table_text) > max_chars:
                # Try to split table by rows (each row on its own line)
                table_rows = table_text.split("\n")
                
                # Keep header and separator
                if len(table_rows) >= 3:
                    header = "\n".join(table_rows[:2])  # Header + separator
                    
                    current_table = header
                    for row in table_rows[2:]:
                        if len(current_table) + len(row) + 1 > max_chars:
                            # Flush current table chunk
                            chunks.append({
                                "title": title,
                                "filepath": filepath,
                                "page": block["page"],
                                "section_path": " > ".join(section_path[-3:]),
                                "content": current_table,
                                "content_markdown": current_table,
                                "bbox": block.get("bbox")
                            })
                            # Start new table chunk with header
                            current_table = header + "\n" + row
                        else:
                            current_table += "\n" + row
                    
                    # Flush remaining
                    if current_table != header:
                        chunks.append({
                            "title": title,
                            "filepath": filepath,
                            "page": block["page"],
                            "section_path": " > ".join(section_path[-3:]),
                            "content": current_table,
                            "content_markdown": current_table,
                            "bbox": block.get("bbox")
                        })
                else:
                    # Can't split intelligently, just truncate or split by chars
                    table_chunks = recursive_split_text(table_text, max_chars)
                    for tc in table_chunks:
                        chunks.append({
                            "title": title,
                            "filepath": filepath,
                            "page": block["page"],
                            "section_path": " > ".join(section_path[-3:]),
                            "content": tc,
                            "content_markdown": tc,
                            "bbox": block.get("bbox")
                        })
            else:
                # Table fits in one chunk
                chunks.append({
                    "title": title,
                    "filepath": filepath,
                    "page": block["page"],
                    "section_path": " > ".join(section_path[-3:]),
                    "content": table_text,
                    "content_markdown": table_md,
                    "bbox": block.get("bbox")
                })
            
            continue
        
        elif block_type in ("codeblock", "figure", "formula"):
            # Keep these atomic like tables; no semantic overlap.
            flush_paragraphs()
            
            body = text  # already markdown from DI / splitter
            if len(body) > max_chars:
                # Rare, but split safely if huge (e.g., very large code blocks or long captions)
                for tc in recursive_split_text(body, max_chars):
                    chunks.append({
                        "title": title,
                        "filepath": filepath,
                        "page": block.get("page", current_page),
                        "section_path": " > ".join(section_path[-3:]),
                        "content": tc,
                        "content_markdown": tc,
                        "bbox": block.get("bbox")
                    })
            else:
                chunks.append({
                    "title": title,
                    "filepath": filepath,
                    "page": block.get("page", current_page),
                    "section_path": " > ".join(section_path[-3:]),
                    "content": body,
                    "content_markdown": body,
                    "bbox": block.get("bbox")
                })
            continue
        
        elif block_type == "paragraph":
            # Determine the page for this block
            new_page = block.get("page", current_page)
            
            # If the buffer exists and this paragraph is on a new page, flush first
            if paragraph_buffer and new_page != paragraph_buffer[-1].get("page"):
                flush_paragraphs()
            
            # Accumulate paragraph with its page
            paragraph_buffer.append({**block, "page": new_page})
            current_page = new_page
            continue
    
    # Flush any remaining paragraphs
    flush_paragraphs()
    
    return chunks
