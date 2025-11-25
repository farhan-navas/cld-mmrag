# Multimodal RAG

Multimodal Retrieval‑Augmented Generation (RAG) system that lets subject‑matter experts interrogate PDFs, Office docs, and images while receiving cite-as-you-answer responses grounded in their own corpus.

---

## Architecture / System Design

| Layer                              | Responsibilities                                                                                                           | Key Files                                                                      |
| ---------------------------------- | -------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------ |
| **Frontend (Streamlit)**           | Chat UI, costing toggle, document links, status indicators.                                                                | `frontend/streamlit_app.py`                                                    |
| **Backend API / Agents (FastAPI)** | Receives chat turns, orchestrates query rewrite + main agent, enforces cost/non-cost policies, routes tool invocations.    | `app/main.py`, `app/agents/main_agent.py`, `app/agents/query_rewrite_agent.py` |
| **Retrieval Layer**                | Azure AI Search hybrid search across standard + cost indices, chunk fetch tools, math/table utilities.                     | `app/tools/*.py`, `app/models.py`, `app/schema.py`                             |
| **Ingestion Pipeline**             | SharePoint sync, MarkItDown + Azure Document Intelligence extraction, normalization + chunking, embeddings, index upserts. | `app/ingestion/**` (see dedicated README)                                      |
| **External Services**              | Azure AI Search, Azure OpenAI, Azure Document Intelligence, SharePoint Graph, optional Florence/vision models.             | configured via `.env` / `app/config.py`                                        |

**Execution flow**

1. User submits a question in the Streamlit UI along with the "Cost Team" toggle.
2. FastAPI receives the request, calls the query-rewrite agent for clarifications, then hands the prompt to the main agent with guardrails.
3. The agent decides which tools to call (search, chunk fetch, math eval, etc.), injecting the correct search index (standard vs. cost) based on the toggle.
4. Retrieved chunks + metadata are fused into a grounded response with inline citations.
5. Background ingestion jobs keep Azure AI Search up-to-date by chunking new/changed documents and pushing embeddings.

## Installation

1. **Prerequisites**
   - Python 3.13
   - `uv` (recommended) or `pip`
   - Azure resources: AI Search, OpenAI deployment, Document Intelligence (if using DI-first mode), SharePoint app registration
2. **Clone & enter the repo**
   ```bash
   git clone https://github.com/farhan-navas/cld-mmrag.git
   cd cld-mmrag
   ```
3. **Create environment**
   ```bash
   uv sync
   ```
4. **Configure secrets**
   - Copy `.env.example` to `.env` (create one if not provided).
   - Fill in `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_API_KEY`, `AZURE_OPENAI_ENDPOINT`, `AZURE_OPENAI_API_KEY`, `AZURE_DOC_INTELLIGENCE_*`, SharePoint creds, etc.
   - Optional knobs:
     - `INDEXING_EXTRACTOR=markitdown|di` (primary extractor; whichever you pick auto-falls back to the other)
     - `MODEL_CHOICE=florence2|phi3-vision`
     - Logging toggles (`LOG_LEVEL`, `LOG_TO_CONSOLE`).

## Running the application

1. **Start the FastAPI backend**
   ```bash
   uv run uvicorn app.main:app --reload
   ```
2. **Start the Streamlit UI**
   ```bash
   uv run streamlit run frontend/streamlit_app.py
   ```
3. **Chat workflow**
   - Use the sidebar toggle "Is costing team member" to include cost-index data.
   - Ask questions; responses show citations linking to the document viewer endpoint.
4. **Background jobs**
   - To run ingestion manually: `uv run python -m app.ingestion.run_ingestion`
   - Incremental SharePoint sync: `uv run python -m app.ingestion.ingestion_incremental_load`

## Scripts & Functions Overview

| Location                                | Entry point                | Purpose                                                                       |
| --------------------------------------- | -------------------------- | ----------------------------------------------------------------------------- |
| `app/main.py`                           | `FastAPI` app              | Request routing, health checks, chat endpoint.                                |
| `app/agents/main_agent.py`              | `run_agent()`              | Core reasoning agent, tool selection, cost-mode enforcement.                  |
| `app/agents/query_rewrite_agent.py`     | `rewrite_query()`          | Clarifies/expands user queries before retrieval.                              |
| `app/tools/search_docs.py`              | `search_docs()`            | Hybrid keyword/semantic search across Azure AI Search indices.                |
| `app/tools/fetch_chunks.py`             | `fetch_chunks()`           | Fetches cited chunks by `doc_id` for grounding.                               |
| `app/tools/table_qa.py`, `math_eval.py` | Utility tools              | Table math + arithmetic helpers referenced by the agent.                      |
| `app/ingestion/run_ingestion.py`        | `main()`                   | Batch ingestion orchestrator (ensure index, scan data, chunk, embed, upload). |
| `app/ingestion/doc_processor.py`        | `process_file_to_chunks()` | Handles per-file extraction, chunking, embedding glue.                        |
| `scripts/*.py`                          | CLI helpers                | Conversions (PDF→JSON, JSON→Excel), validation utilities.                     |

For ingestion specifics see `app/ingestion/README.md`.

## Code Explanation & Workflow

- **Extractor selection**: Configurable MarkItDown ↔ Document Intelligence pipeline. The selected extractor runs first; if it returns no content or throws, we automatically fall back to the other. This keeps ingestion resilient even if DI is firewall-blocked or MarkItDown lacks a converter.
- **Chunk normalization**: `app/ingestion/indexer/chunking/normalizer.py` removes Markdown artifacts, converts tables to plain text, and ensures consistent whitespace before indexing.
- **Chunking strategies**: PDFs/DOCX/images use `chunk_blocks`; Excel and PowerPoint have dedicated chunkers to preserve sheet/slide structure. Code blocks, tables, and figures are handled as atomic units.
- **Dual-index routing**: Tools and prompts respect a "standard" vs. "cost" index. The Streamlit toggle sets `is_cost_team_member`; the backend injects the proper index name and enforces refusal rules when users lack cost clearance.
- **Tool orchestration**: The main agent follows a tool-augmented plan—search, fetch, optional math/table reasoning—before drafting an answer with citations. Prompts enforce that unauthorized cost requests are declined.
- **SharePoint ingestion**: Files are streamed down, hashed, processed into chunks, embedded via Azure OpenAI, and uploaded to Azure AI Search. Incremental ingestion tracks doc keys for deletes/updates.

## Demo

| Artifact                 | Description                                                                                                                                          |
| ------------------------ | ---------------------------------------------------------------------------------------------------------------------------------------------------- |
| Screenshot (placeholder) | Add a PNG/GIF under `docs/images/demo-chat.png` showing the Streamlit UI with citations.                                                             |
| Sample Q&A               | “What is the refund tender deposit process?” → Response citing `QR-PD-33 Refund Tender Deposit Memo`, referencing the chunk path and shareable link. |
| Cost toggle walkthrough  | Two short bullets explaining how enabling the toggle switches indices and how unauthorized requests are rejected with a templated message.           |

## Next Steps

- Integrate Florence-based embeddings for late interaction.
- Expand ingestion monitors to alert on extractor fallbacks.
- Automate deployment with AZD once IaC is finalized.

For a deep dive into ingestion stages, configuration, and troubleshooting, continue to [`app/ingestion/README.md`](app/ingestion/README.md).
