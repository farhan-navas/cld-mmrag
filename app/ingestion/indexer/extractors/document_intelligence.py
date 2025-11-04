import logging
from typing import List, Dict, Any
from pathlib import Path

from azure.ai.documentintelligence.models import DocumentContentFormat

from app.ingestion.indexer.clients import di_client

logger = logging.getLogger("indexer.extractors.di")

def table_to_markdown(table) -> str:
    """
    convert a di table to markdown format
    """
    rows = table.row_count or 0
    cols = table.column_count or 0
    if rows <= 0 or cols <= 0:
        return ""
    
    # Pre-size grid
    grid = [["" for _ in range(cols)] for _ in range(rows)]
    
    for cell in (getattr(table, "cells", None) or []):
        text = (getattr(cell, "content", None) or "").strip()
        r0 = getattr(cell, "row_index", 0) or 0
        c0 = getattr(cell, "column_index", 0) or 0
        
        if 0 <= r0 < rows and 0 <= c0 < cols:
            grid[r0][c0] = text
    
    lines = []
    for r, row in enumerate(grid):
        line = "| " + " | ".join(row) + " |"
        lines.append(line)
        if r == 0:
            lines.append("| " + " | ".join("---" for _ in row) + " |")
    return "\n".join(lines)

def slice_markdown_from_spans(result, spans) -> str:
    """
    extract markdown text from di result using spans
    """
    if not spans:
        return ""
    parts = []
    for s in sorted(spans, key=lambda s: (getattr(s, "offset", 0) or 0)):
        off = getattr(s, "offset", None)
        ln = getattr(s, "length", None)
        if isinstance(off, int) and isinstance(ln, int) and off >= 0 and ln > 0:
            parts.append(result.content[off:off+ln])
    return "".join(parts).strip()


def extract_blocks_with_di(file_path: Path) -> List[Dict[str, Any]]:
    cli = di_client()
    
    ct_map = {
        ".pdf": "application/pdf",
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".tif": "image/tiff",
        ".tiff": "image/tiff",
        ".bmp": "image/bmp",
        ".docx": "application/octet-stream",
        ".pptx": "application/octet-stream",
    }
    
    ctype = ct_map.get(file_path.suffix.lower(), "application/octet-stream")
    
    with open(file_path, "rb") as f:
        poller = cli.begin_analyze_document(
            model_id="prebuilt-layout",
            body=f,
            output_content_format=DocumentContentFormat.MARKDOWN,
            content_type=ctype,
        )
    result = poller.result()
    blocks: List[Dict[str, Any]] = []
    
    # Extract paragraphs/headings
    for para in (getattr(result, "paragraphs", None) or []):
        text = (getattr(para, "content", None) or "").strip()
        if not text:
            continue
        page = para.bounding_regions[0].page_number if getattr(para, "bounding_regions", None) else 1
        kind = (getattr(para, "role", None) or "").lower()
        blocks.append({
            "type": "heading" if ("heading" in kind or "title" in kind) else "paragraph",
            "text": text,
            "markdown": None,
            "page": page,
            "bbox": None,
        })
    
    # Extract tables
    has_doc_markdown = bool(getattr(result, "content", None))
    for table in (getattr(result, "tables", None) or []):
        page = table.bounding_regions[0].page_number if getattr(table, "bounding_regions", None) else 1
        
        # Try extracting from spans, fallback to cell-based rendering
        md = slice_markdown_from_spans(result, getattr(table, "spans", None)) if has_doc_markdown else ""
        
        if not md:
            md = table_to_markdown(table)
        
        if md.strip():
            blocks.append({
                "type": "table",
                "text": md,
                "markdown": md,
                "page": page,
                "bbox": None
            })
    
    # Extract figures
    for fig in (getattr(result, "figures", None) or []):
        page = fig.bounding_regions[0].page_number if getattr(fig, "bounding_regions", None) else 1
        md = slice_markdown_from_spans(result, getattr(fig, "spans", None)) or (getattr(fig, "caption", None) or "").strip()
        if md:
            blocks.append({
                "type": "figure",
                "text": md,
                "markdown": md,
                "page": page,
                "bbox": None
            })
    
    # Extract formulas
    for fm in (getattr(result, "formulas", None) or []):
        page = fm.bounding_regions[0].page_number if getattr(fm, "bounding_regions", None) else 1
        md = slice_markdown_from_spans(result, getattr(fm, "spans", None)) or (getattr(fm, "value", None) or "").strip()
        if md:
            blocks.append({
                "type": "formula",
                "text": md,
                "markdown": md,
                "page": page,
                "bbox": None
            })
    
    # Fallback: if DI gave nothing structured, take whole-doc markdown
    if not blocks and getattr(result, "content", None):
        blocks = [{
            "type": "paragraph",
            "text": result.content,
            "markdown": result.content,
            "page": 1,
            "bbox": None
        }]
    
    return blocks
