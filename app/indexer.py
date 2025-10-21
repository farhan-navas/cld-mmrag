import os, uuid, logging
from typing import List, Dict, Any
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

logger = logging.getLogger("agent")

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


# ---------- Chunking ----------
def chunk_blocks(blocks: List[Dict[str, Any]], title: str, filepath: str) -> List[Dict[str, Any]]:
    max_chars = config.indexing.chunk_max_chars
    overlap = config.indexing.chunk_overlap_chars

    chunks, buf, buf_len, section_path = [], [], 0, []

    def flush():
        nonlocal buf, buf_len
        if not buf:
            return
        text = "\n\n".join(x["text"] for x in buf)
        md_parts = [x.get("markdown") for x in buf if x.get("markdown")]
        md = "\n\n".join(md_parts) if md_parts else None
        page = buf[0]["page"]
        chunks.append({
            "title": title,
            "filepath": filepath,
            "page": page,
            "section_path": " > ".join(section_path[-3:]),
            "content": text,
            "content_markdown": md,
            "bbox": None
        })
        # overlap
        if overlap > 0:
            keep, running = [], 0
            for b in reversed(buf):
                running += len(b["text"]) + 2
                keep.append(b)
                if running >= overlap:
                    break
            buf = list(reversed(keep))
            buf_len = sum(len(b["text"]) + 2 for b in buf)
        else:
            buf, buf_len = [], 0

    for b in blocks:
        t = b["type"]
        txt = (b.get("text") or "").strip()
        if not txt:
            continue

        if t == "heading":
            flush()
            section_path.append(txt[:120])
            if len(section_path) > 8:
                section_path = section_path[-8:]
            continue

        if t == "table":
            flush()
            chunks.append({
                "title": title,
                "filepath": filepath,
                "page": b["page"],
                "section_path": " > ".join(section_path[-3:]),
                "content": txt,
                "content_markdown": b.get("markdown"),
                "bbox": b.get("bbox")
            })
            continue

        if buf_len + len(txt) + 2 > max_chars:
            flush()
        buf.append(b)
        buf_len += len(txt) + 2

    flush()
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
            chunks = chunk_blocks(blocks, title=path.stem, filepath=str(path.resolve()))
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