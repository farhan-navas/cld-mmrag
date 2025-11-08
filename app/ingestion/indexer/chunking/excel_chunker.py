"""
Excel chunking strategy.

This module handles chunking of Excel files with row-wise batching
and column grouping for wide tables.
"""

import logging
import json
from typing import List, Dict, Any
from pathlib import Path

from app.config import config
from app.ingestion.indexer.chunking.text_splitter import recursive_split_text

logger = logging.getLogger("indexer.chunking.excel")


def chunk_xlsx(path: Path, title: str, filepath: str) -> List[Dict[str, Any]]:
    """
    Chunk Excel files with row-wise batching and column grouping for wide tables.
    Preserves table semantics and includes summary chunks per sheet.
    
    :param path: Path to the Excel file
    :param title: Document title
    :param filepath: Filepath for metadata
    :return: List of chunk dictionaries
    """
    try:
        import pandas as pd
    except ImportError:
        logger.error("pandas is required for Excel processing. Install with: pip install pandas openpyxl")
        return []
    
    chunks = []
    max_chars = config.indexing.chunk_max_chars
    ROWS_PER_CHUNK = config.indexing.xlsx_rows_per_chunk
    COLS_PER_GROUP = config.indexing.xlsx_cols_per_group
    
    try:
        xl = pd.ExcelFile(path)
    except Exception as e:
        logger.warning(f"Failed to load Excel file {path.name}: {e}")
        return []
    
    for sheet_name in xl.sheet_names:
        try:
            df = xl.parse(sheet_name)
            
            # Clean column names
            df.columns = [str(c) for c in df.columns]
            
            # Create summary chunk for the sheet
            col_preview = ", ".join(map(str, df.columns[:min(10, len(df.columns))]))
            summary = (
                f"[Sheet] {sheet_name} | rows={len(df)}, cols={len(df.columns)} | "
                f"columns: {col_preview}"
            )
            chunks.append({
                "title": title,
                "filepath": filepath,
                "page": 1,
                "section_path": f"Excel > {sheet_name}",
                "content": summary,
                "content_markdown": summary,
                "bbox": None,
                "metadata_json": json.dumps({
                    "filetype": "xlsx",
                    "sheet_name": sheet_name,
                    "is_summary": True
                })
            })
            
            # If wide, split columns into groups
            col_groups = [df.columns[i:i+COLS_PER_GROUP].tolist() 
                         for i in range(0, len(df.columns), COLS_PER_GROUP)]
            
            for col_group_idx, cg in enumerate(col_groups):
                sub = df[cg].copy()
                
                # Add row index column for context
                sub.insert(0, 'Row', range(len(sub)))
                
                # Row-batch loop
                for r0 in range(0, len(sub), ROWS_PER_CHUNK):
                    r1 = min(len(sub), r0 + ROWS_PER_CHUNK)
                    batch = sub.iloc[r0:r1]
                    
                    # Render to Markdown table
                    try:
                        md = batch.to_markdown(index=False)
                    except Exception as e:
                        logger.warning(f"Failed to convert batch to markdown for sheet {sheet_name}: {e}")
                        continue
                    
                    # If it exceeds max_chars, fall back to recursive split
                    if len(md) > max_chars:
                        for tc in recursive_split_text(md, max_chars):
                            chunks.append({
                                "title": title,
                                "filepath": filepath,
                                "page": 1,
                                "section_path": f"Excel > {sheet_name}",
                                "content": tc,
                                "content_markdown": tc,
                                "bbox": None,
                                "metadata_json": json.dumps({
                                    "filetype": "xlsx",
                                    "sheet_name": sheet_name,
                                    "row_start": r0,
                                    "row_end": r1,
                                    "col_group": col_group_idx
                                })
                            })
                    else:
                        chunks.append({
                            "title": title,
                            "filepath": filepath,
                            "page": 1,
                            "section_path": f"Excel > {sheet_name}",
                            "content": md,
                            "content_markdown": md,
                            "bbox": None,
                            "metadata_json": json.dumps({
                                "filetype": "xlsx",
                                "sheet_name": sheet_name,
                                "row_start": r0,
                                "row_end": r1,
                                "col_group": col_group_idx
                            })
                        })
        
        except Exception as e:
            logger.warning(f"Failed to process sheet '{sheet_name}' in {path.name}: {e}")
            continue
    
    return chunks
