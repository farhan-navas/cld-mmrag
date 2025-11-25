# Ingestion Pipeline

This ingestion pipeline automates watching the folders you care about, pulls anything new or updated, cleans and chunks the content, and keeps both the standard and cost Azure AI Search indices aligned.

---

```
Discovery --> Extraction --> Chunking --> Embedding --> Indexing
   |           |               |              |            \
   |           |               |              |             -> Azure AI Search stays in sync
   \-> SharePoint + local sources feed a single temp workspace
```

---

### Full batch ingestion

```bash
uv run python -m app.ingestion.run_ingestion
```

- Ensures the search index exists.
- Processes each file through extractor + chunker + embedding.
- Uploads chunks in batches.

### Standalone utilities

- `scripts/convert-json-to-excel.py`, `scripts/convert-pdf-to-json.py`, `scripts/validate_queries.py` help prepare corpora.
- You can also take a look at `app/check_index.ipynb` which provides the main utilities required to run

---

## Workflow Details

1. **Block extraction**
   - `_try_extractor` first calls the configured extractor (MarkItDown or DI) and automatically retries with the other on errors/empty output.
   - Normalization removes markdown artifacts, renders tables with `render_plain_table`, and standardizes whitespace.
2. **Chunking**
   - PDF/DOCX/images: `chunk_blocks` respects headings, table boundaries, code blocks, and page numbers.
   - Excel: `chunk_xlsx` groups sheets, rows, and columns according to config to keep tables intact.
   - PowerPoint: `chunk_pptx` merges slide titles, body text, and optional notes.
3. **Embedding**
   - `doc_processor.embed_chunks` batches content, truncates to 8k characters, and requests embeddings from Azure OpenAI.
4. **Upload / delete**
   - `uploader.upsert_chunks` sends batches to Azure AI Search.
   - `doc_processor.prepare_documents_for_upload` assigns stable IDs per doc + chunk, enabling deletions by `doc_key`.

---

## Key Files & Responsibilities

- MAIN ONE TO USE: Use `app/ingestion/run_ingestion.py` when you want the one-button SharePoint sync—it validates config, selects the folder/mapping sheet, and hands control to the incremental runner
- Use `app/ingestion/ingestion_incremental_load.py` when you need to customize how files are compared, deleted, or reprocessed; it ties discovery, diffing, and uploads together.
- Use `app/ingestion/doc_processor.py` when experimenting with per-file behavior; it exposes the extract -> chunk -> embed -> upload steps as standalone helpers.
- Use `app/ingestion/sharepoint_api.py` to debug Microsoft Graph access or plug in alternative folder discovery logic (token fetch, recursion, downloads).
- Use `app/ingestion/indexer/` when adjusting extractors, chunkers, or the Azure Search schema—the subpackages contain MarkItDown/DI adapters, text splitters, and uploader utilities.

---

## Some Final Tips

- If you would like to change your RAG index, remember to update the root `config.py` file but also remember to change the `MAPPING_FILE` variable inside `app/ingestion/run_ingestion.py`.
