import logging, time
from typing import List, Dict, Set
from collections import defaultdict

from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import ResourceNotFoundError
from azure.search.documents import SearchClient

from config import config
from tools.models import FetchInput, FetchOutput, Chunk

logger = logging.getLogger("tool.fetch_chunks")

def _search_client() -> SearchClient:
    return SearchClient(
        config.ai_search.endpoint,
        config.ai_search.index_name,
        AzureKeyCredential(config.ai_search.api_key)
    )

def fetch_chunks(inp: FetchInput) -> FetchOutput:
    logger.info("fetch_chunks start ids=%d", len(inp.ids or []))

    sc = _search_client()
    if not inp.ids:
        return FetchOutput(chunks=[])

    first_selected = ["id", "doc_key", "chunk_index"]
    selected = ["id", "doc_key", "chunk_index", "title", "page", "section_path", "content", "content_markdown"]

    t0 = time.perf_counter()
    
    # here we figure out what are the main chunks AND we retrieve only doc_key + chunk_index
    req_chunks: Dict[str, dict] = {}
    try:
        for doc_id in inp.ids:
            try:
                r = sc.get_document(key=doc_id, selected_fields=first_selected)
                req_chunks[doc_id] = r

                if "doc_key" not in r:
                    logger.warning(f"Document {doc_id} missing doc_key field - may be old document")

            except ResourceNotFoundError:
                logger.warning("fetch_chunks missing id=%s", doc_id)

        logger.info("fetch_chunks ok results=%d in %.1f ms",
                    len(req_chunks), (time.perf_counter() - t0) * 1000)
    except Exception:
        logger.exception("fetch_chunks get_document failed after %.1f ms",
                         (time.perf_counter() - t0) * 1000)
        raise

    # now we get just add the next 5 docs, use set property to make sure no duplicated for the same
    # doc id!
    chunks_needed: Dict[str, Set[int]] = defaultdict(set)
    for doc_id in inp.ids:
        if doc_id not in req_chunks:
            continue
        r = req_chunks[doc_id]
        doc_key = r.get("doc_key")
        chunk_idx = r.get("chunk_index")

        if doc_key is None or chunk_idx is None:
            logger.warning("fetch_chunks chunk %s missing doc_key or chunk_index", doc_id)
            continue

        chunks_needed[doc_key].add(chunk_idx)

        for offset in range(1, 6):
            chunks_needed[doc_key].add(chunk_idx + offset)

    final_chunks: List[Chunk] = []
    seen_ids: Set[str] = set()
    t1 = time.perf_counter()

    for doc_key, indices in chunks_needed.items():
        if not indices:
            continue
            
        # Build filter: doc_key eq 'X' and chunk_index in (i1, i2, ...)
        indices_str = " or ".join([f"chunk_index eq {idx}" for idx in sorted(indices)])
        filter_expr = f"doc_key eq '{doc_key}' and ({indices_str})"

        try:
            results = list(sc.search(
                search_text="*",
                filter=filter_expr,
                select=selected,
                top=len(indices),
            ))

            for r in results:
                chunk_id = r["id"]
                if chunk_id in seen_ids:
                    continue
                seen_ids.add(chunk_id)

                final_chunks.append(Chunk(
                    id=r["id"],
                    doc_key=r["doc_key"],
                    chunk_index=r["chunk_index"],
                    title=r.get("title","") or "",
                    page=int(r.get("page",1) or 1),
                    section_path=r.get("section_path","") or "",
                    content=r.get("content","") or "",
                    content_markdown=r.get("content_markdown")
                ))
                
            logger.debug("fetch_chunks fetched %d chunks for doc_key=%s", len(results), doc_key)
        except Exception as e:
            logger.exception("fetch_chunks batch query failed for doc_key=%s: %s", doc_key, e)
    
    logger.info("fetch_chunks fetched %d total chunks (incl. consecutive) in %.1f ms",
                len(final_chunks), (time.perf_counter() - t1) * 1000)

    # keep original order roughly: sort by the order of inp.ids
    order = {k:i for i,k in enumerate(inp.ids)}
    final_chunks.sort(key=lambda c: order.get(c.id, 10**9))

    return FetchOutput(chunks=final_chunks)
