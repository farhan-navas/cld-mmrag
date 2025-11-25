# Ingestion Pipeline

End-to-end process that keeps Azure AI Search synchronized with documents stored in SharePoint and local `data/preprocessed` folders.

---

## Overview

1. **Discovery** – Locate eligible files via SharePoint APIs or on-disk paths.
2. **Extraction** – Convert documents into normalized text blocks using MarkItDown and/or Azure Document Intelligence (DI).
3. **Chunking** – Apply format-aware chunkers (PDF/DOCX, Excel, PowerPoint) with table/code preservation.
4. **Embedding** – Generate vector representations via Azure OpenAI embeddings.
5. **Indexing** – Upsert chunk metadata + vectors to the standard and/or cost Azure AI Search indices.

The pipeline is resilient to extractor failures: whichever extractor (MarkItDown or DI) you select as primary automatically falls back to the other when no content or errors occur.

---

## Key Components

| Module                                        | Purpose                                                                                                    |
| --------------------------------------------- | ---------------------------------------------------------------------------------------------------------- |
| `app/ingestion/run_ingestion.py`              | Batch orchestrator; validates config, walks `data/preprocessed`, routes files to chunkers, uploads chunks. |
| `app/ingestion/doc_processor.py`              | Per-file workflow (extract → chunk → embed).                                                               |
| `app/ingestion/ingestion_incremental_load.py` | SharePoint incremental sync + doc-key tracking.                                                            |
| `app/ingestion/indexer/extractors/`           | MarkItDown + DI extractors, Excel + PowerPoint helpers.                                                    |
| `app/ingestion/indexer/chunking/`             | Normalizers, text splitters, format-specific chunking strategies.                                          |
| `app/ingestion/indexer/uploader.py`           | Handles Azure AI Search upserts/deletes in batches.                                                        |

---

### Full batch ingestion

```bash
uv run python -m app.ingestion.run_ingestion
```

- Ensures the search index exists.
- Scans `data/preprocessed/**` for supported extensions.
- Processes each file through extractor + chunker + embedding.
- Uploads chunks in batches.

### Standalone utilities

- `scripts/convert-json-to-excel.py`, `scripts/convert-pdf-to-json.py`, `scripts/validate_queries.py` help prepare corpora.
- You can also take a look at playg.ipynb which provides the main utilities required to run

---

## Workflow Details

1. **Download / discovery**
   - SharePoint API stores files under a temp folder, tracking `sharepoint_relative_path` metadata.
2. **Block extraction**
   - `_try_extractor` first calls the configured extractor (MarkItDown or DI) and automatically retries with the other on errors/empty output.
   - Normalization removes markdown artifacts, renders tables with `render_plain_table`, and standardizes whitespace.
3. **Chunking**
   - PDF/DOCX/images: `chunk_blocks` respects headings, table boundaries, code blocks, and page numbers.
   - Excel: `chunk_xlsx` groups sheets, rows, and columns according to config to keep tables intact.
   - PowerPoint: `chunk_pptx` merges slide titles, body text, and optional notes.
4. **Embedding**
   - `doc_processor.embed_chunks` batches content, truncates to 8k characters, and requests embeddings from Azure OpenAI.
5. **Upload / delete**
   - `uploader.upsert_chunks` sends batches to Azure AI Search.
   - `doc_processor.prepare_documents_for_upload` assigns stable IDs per doc + chunk, enabling deletions by `doc_key`.

---

## Sample Log Excerpt

```
INFO  [run_ingestion] Using extractor mode markitdown
INFO  [doc_processor] Processing file: QR-PD-33 Refund Memo.docx
INFO  [indexer.extractors] Starting MarkItDown extraction for QR-PD-33 Refund Memo.docx
WARNING[indexer.extractors] MarkItDown extractor returned no content... Falling back to Document Intelligence
INFO  [indexer.extractors] Starting Document Intelligence extraction...
INFO  [doc_processor]   - Extracted 42 blocks
INFO  [doc_processor]   - Created 18 chunks
INFO  [doc_processor] Embedding 18 chunks...
INFO  [indexer.uploader] Uploaded batch 1
```

---
