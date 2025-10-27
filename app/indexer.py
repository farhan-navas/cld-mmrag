import os, uuid, logging, re
from typing import List, Dict, Any, Optional
from pathlib import Path
from collections import defaultdict

# Azure SDKs 
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType,
    SimpleField, SearchableField, VectorSearch, HnswAlgorithmConfiguration,
    VectorSearchProfile, HnswParameters, SearchSuggester
)

from azure.search.documents import SearchClient
from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import DocumentContentFormat

from openai import AzureOpenAI
from config import config

logger = logging.getLogger("indexer")

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# Allow override via env, else default to <repo>/data/preprocessed
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data" / "preprocessed")).resolve()

def search_index_client():
    return SearchIndexClient(
        config.ai_search.endpoint,
        AzureKeyCredential(config.ai_search.api_key)
    )

def search_client():
    return SearchClient(
        config.ai_search.endpoint,
        config.ai_search.index_name,
        AzureKeyCredential(config.ai_search.api_key)
    )

def di_client():
    return DocumentIntelligenceClient(
        config.doc_intelligence.endpoint,
        AzureKeyCredential(config.doc_intelligence.api_key)
    )

def aoai_client():
    return AzureOpenAI(
        api_key=config.openai.api_key,
        api_version=config.openai.api_version,
        azure_endpoint=config.openai.endpoint,
    )

# Embeddings 
def get_embedding(texts: List[str]) -> List[List[float]]:
    logger.info("[START] embedding")
    client = aoai_client()
    resp = client.embeddings.create(
        input=texts,
        model=config.openai.embedding_model
    )

    return [d.embedding for d in resp.data]

def embedding_dimension() -> int:
    return len(get_embedding(["dim probe"])[0])

# Index creation 
def ensure_index():
    sic = search_index_client()
    idx_name = config.ai_search.index_name
    try:
        sic.get_index(idx_name)
        print(f"Index '{idx_name}' exists.")
        return
    except Exception:
        pass

    dims = embedding_dimension()

    hnsw = HnswAlgorithmConfiguration(
        name="hnsw",
        parameters=HnswParameters(m=4, ef_construction=400, ef_search=100)
    )
    vs = VectorSearch(
        algorithms=[hnsw],
        profiles=[VectorSearchProfile(name="default", algorithm_configuration_name="hnsw")]
    )
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="doc_key", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="chunk_index", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SearchableField(name="title", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SearchableField(name="filepath", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SearchableField(name="section_path", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchableField(name="content_markdown", type=SearchFieldDataType.String),
        # vector field
        SearchField(
            name="contentVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=dims,
            vector_search_profile_name="default",
        ),
        SearchableField(name="bbox", type=SearchFieldDataType.String),
        SearchableField(name="metadata_json", type=SearchFieldDataType.String),
    ]
    index = SearchIndex(
        name=idx_name,
        fields=fields,
        vector_search=vs,
        suggesters=[SearchSuggester(name="sg", source_fields=["title", "content"])]
    )
    sic.create_index(index)
    print(f"Created index '{idx_name}'.")

# ---------- DI extraction ----------
def table_to_markdown(table) -> str:
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

        # TODO: Normalize spans (they can be None) 
        # r_span = getattr(cell, "row_span", 1) or 1
        # c_span = getattr(cell, "column_span", 1) or 1

        # Place text at the top-left of the (possibly merged) region
        if 0 <= r0 < rows and 0 <= c0 < cols:
            grid[r0][c0] = text
        # (Optional) You could also fill the spanned area or add markers.

    # Render Markdown (simple rule after header row)
    lines = []
    for r, row in enumerate(grid):
        line = "| " + " | ".join(row) + " |"
        lines.append(line)
        if r == 0:
            lines.append("| " + " | ".join("---" for _ in row) + " |")
    return "\n".join(lines)

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
        ".docx": "application/octet-stream", # for office files: either preconvert to PDF or pass octet-stream
        ".pptx": "application/octet-stream",
    }

    ctype = ct_map.get(file_path.suffix.lower(), "application/octet-stream")

    with open(file_path, "rb") as f:
        poller = cli.begin_analyze_document(
            model_id="prebuilt-layout",
            body=f,  # <-- bytes stream
            output_content_format=DocumentContentFormat.MARKDOWN,
            content_type=ctype,
        )
    result = poller.result()
    blocks: List[Dict[str, Any]] = []

    # paragraphs/headings
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

    # tables: prefer slicing from `result.content` via spans; fall back to cells renderer
    has_doc_markdown = bool(getattr(result, "content", None))
    for table in (getattr(result, "tables", None) or []):
        page = table.bounding_regions[0].page_number if getattr(table, "bounding_regions", None) else 1
        md = ""

        if has_doc_markdown and getattr(table, "spans", None):
            # Guard spans: offset/length might be None on rare docs
            parts = []
            for s in table.spans:
                off = getattr(s, "offset", None)
                ln  = getattr(s, "length", None)
                if isinstance(off, int) and isinstance(ln, int) and ln > 0:
                    parts.append(result.content[off:off+ln])
            md = "".join(parts).strip()

        if not md:
            # Fallback to robust cell-based markdown
            md = table_to_markdown(table)

        if md.strip():
            blocks.append({
                "type": "table",
                "text": md,
                "markdown": md,
                "page": page,
                "bbox": None
            })

    # fallback: if DI gave nothing structured, take whole-doc markdown
    if not blocks and getattr(result, "content", None):
        blocks = [{
            "type": "paragraph",
            "text": result.content,
            "markdown": result.content,
            "page": 1,
            "bbox": None
        }]
    return blocks


# ---------- Recursive Chunking ----------
def recursive_split_text(text: str, max_chars: int, separators: Optional[List[str]] = None) -> List[str]:
    """
    Recursively split text using a hierarchy of separators.
    Tries to keep semantic units together as much as possible.
    
    Args:
        text: Text to split
        max_chars: Maximum characters per chunk
        separators: List of separators to try in order (most semantic to least)
    
    Returns:
        List of text chunks
    """
    if separators is None:
        # Default hierarchy: paragraph → sentence → clause → word
        separators = [
            "\n\n",      # Paragraph breaks
            "\n",        # Line breaks
            ". ",        # Sentences
            "! ",        # Exclamations
            "? ",        # Questions
            "; ",        # Clauses
            ", ",        # Phrases
            " ",         # Words
            ""           # Characters (last resort)
        ]
    
    # Base case: text fits in max_chars
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    
    # Try each separator in order
    for i, sep in enumerate(separators):
        if sep == "":
            # Last resort: split by characters
            chunks = []
            for j in range(0, len(text), max_chars):
                chunks.append(text[j:j + max_chars])
            return chunks
        
        if sep in text:
            # Split by this separator
            splits = text.split(sep)
            
            # Reconstruct chunks respecting max_chars
            chunks = []
            current_chunk = ""
            
            for split in splits:
                # Re-add separator (except for last split)
                piece = split + sep if split != splits[-1] else split
                
                # If this single piece is too large, recurse with next separator
                if len(piece) > max_chars:
                    # Flush current chunk first
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                        current_chunk = ""
                    # Recurse on the large piece
                    sub_chunks = recursive_split_text(piece, max_chars, separators[i+1:])
                    chunks.extend(sub_chunks)
                    continue
                
                # If adding this piece would exceed max, flush current chunk
                if current_chunk and len(current_chunk) + len(piece) > max_chars:
                    chunks.append(current_chunk.strip())
                    current_chunk = piece
                else:
                    current_chunk += piece
            
            # Flush remaining
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            return chunks
    
    # Fallback (should never reach here)
    return [text]


def create_overlap_chunks(chunks: List[str], overlap_chars: int) -> List[str]:
    """
    Add overlap between consecutive chunks by prepending part of previous chunk.
    
    Args:
        chunks: List of text chunks
        overlap_chars: Number of characters to overlap
    
    Returns:
        List of chunks with overlap
    """
    if not chunks or overlap_chars <= 0:
        return chunks
    
    overlapped = [chunks[0]]  # First chunk has no overlap
    
    for i in range(1, len(chunks)):
        prev_chunk = chunks[i-1]
        current_chunk = chunks[i]
        
        # Get last N chars from previous chunk
        if len(prev_chunk) > overlap_chars:
            overlap_text = prev_chunk[-overlap_chars:]
            # Try to start at a word boundary
            space_idx = overlap_text.find(" ")
            if space_idx > 0:
                overlap_text = overlap_text[space_idx + 1:]
            
            overlapped.append(overlap_text + " [...] " + current_chunk)
        else:
            overlapped.append(current_chunk)
    
    return overlapped


# ---------- Chunking ----------
def chunk_blocks(blocks: List[Dict[str, Any]], title: str, filepath: str) -> List[Dict[str, Any]]:
    """
    Chunk blocks using recursive splitting strategy.
    
    Strategy:
    - Headings: Create section boundaries and hierarchy
    - Tables: Keep as standalone chunks (atomic units)
    - Paragraphs: Use recursive splitting to maintain semantic coherence
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
        
        # Use recursive splitting
        text_chunks = recursive_split_text(combined_text, max_chars)
        
        # Add overlap between chunks
        if overlap > 0:
            text_chunks = create_overlap_chunks(text_chunks, overlap)
        
        # Create chunk records
        page = paragraph_buffer[0]["page"]
        for chunk_text in text_chunks:
            if chunk_text.strip():
                chunks.append({
                    "title": title,
                    "filepath": filepath,
                    "page": page,
                    "section_path": " > ".join(section_path[-3:]),
                    "content": chunk_text,
                    "content_markdown": chunk_text,  # Already in markdown from DI
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
        
        elif block_type == "paragraph":
            # Accumulate paragraphs for recursive chunking
            paragraph_buffer.append(block)
    
    # Flush any remaining paragraphs
    flush_paragraphs()
    
    return chunks

# ---------- Upsert ----------
def _sha1(s: str) -> str:
    import hashlib
    return hashlib.sha1(s.encode("utf-8")).hexdigest()

def upsert_chunks(chunks: List[Dict[str, Any]]):
    sc = search_client()
    eb = config.indexing.embed_batch_size
    ub = config.indexing.upload_batch_size

    by_file = defaultdict(list)
    for ch in chunks:
        by_file[ch["filepath"]].append(ch)

    docs: List[Dict[str, Any]] = []
    for filepath, file_chunks in by_file.items():
        doc_key = _sha1(filepath)

        for idx, ch in enumerate(file_chunks):
            doc_id = str(uuid.uuid4())
            docs.append({
                "id": doc_id,
                "doc_key": doc_key, # groups chunks from the same doc
                "chunk_index": idx, # gives us chunk pos in sequence
                **ch
            })

    # embed in batches
    for i in range(0, len(docs), eb):
        batch = docs[i:i+eb]
        vectors = get_embedding([d["content"][:8000] for d in batch])
        for d, v in zip(batch, vectors):
            d["contentVector"] = v

        # upload in sub-batches if needed
        for j in range(0, len(batch), ub):
            sub = batch[j:j+ub]
            sc.upload_documents(sub)

# ---------- Main ----------
def main():
    if config.validate():   
        print("Nice! Config validated!")
    else:
        raise SystemExit("Missing required env vars.")

    ensure_index()

    print("CWD:", Path.cwd())
    print("DATA_DIR (given):", DATA_DIR, "exists?", DATA_DIR.exists())
    print("DATA_DIR absolute:", DATA_DIR.resolve())

    all_chunks = []
    supported = getattr(config.indexing, "supported_exts")
    for path in DATA_DIR.rglob("*"):
        print("Path here is", path)
        if not path.is_file() or path.suffix.lower() not in supported:
            continue
        print(f"\n[FILE] {path.name}")
        try:
            blocks = extract_blocks_with_di(path)
            print(f"  - blocks: {len(blocks)}")
            if len(blocks) < 1:
                print("  ! No blocks extracted (DI may have returned empty). Skipping.")
                continue
            
            # Store relative path from data/preprocessed
            relative_path = str(path.relative_to(DATA_DIR))
            filepath_str = f"data/preprocessed/{relative_path}"
            
            chunks = chunk_blocks(blocks, title=path.stem, filepath=filepath_str)
            print(f"  - chunks: {len(chunks)}")
            if not chunks:
                print("  ! No chunks produced. Skipping.")
                continue
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"  !! Extract failed: {e}")

    if not all_chunks:
        print("\nNo chunks to upload. Check that your PDFs are readable and DI returns content.")
        return

    # 3) Embed + upload
    print(f"\n[UPLOAD] Embedding and uploading {len(all_chunks)} chunks…")
    upsert_chunks(all_chunks)
    print("[DONE] Indexing complete.")

if __name__ == "__main__":
    main()