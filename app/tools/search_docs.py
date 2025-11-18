from typing import List
import logging, re, time

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from app.config import config
from app.tools.models import SearchInput, SearchOutput, Hit
from app.ingestion.indexer import get_embedding

logger = logging.getLogger("tool.search_docs")

def _search_client(index_name: str) -> SearchClient:
    return SearchClient(
        endpoint=config.ai_search.endpoint,
        index_name=index_name,
        credential=AzureKeyCredential(config.ai_search.api_key),
    )

def _make_snippet(text: str, query: str, length: int = 300) -> str:
    if not text:
        return ""
    q = re.escape(query.split()[0]) if query.strip() else ""
    if q:
        m = re.search(q, text, re.IGNORECASE)
        if m:
            start = max(0, m.start() - length // 2)
            end = min(len(text), start + length)
            return text[start:end].replace("\n", " ")
    return (text[:length]).replace("\n", " ")

def search_docs(inp: SearchInput) -> SearchOutput:
    TOP_K = 100 # for bm25 search and then maybe rerank top 8 or sth like that
    sc = _search_client(inp.index_name)

    # 1) Embed the query
    t0 = time.perf_counter()
    qvec = get_embedding([inp.query])[0]
    logger.debug("embedding[:8]=%s … (len=%d)", qvec[:8], len(qvec))

    # 2) Note: We'll do project filtering in Python after retrieval
    #    Azure Search OData has limited string matching capabilities
    project_filter = None
    if inp.filter:
        logger.info("Will apply project filter in post-processing: %s", inp.filter)
        project_filter = inp.filter

    # 3) Hybrid search (keyword + vector) - no filter applied here
    try:
        logger.info("AZSEARCH request query=%r top_k=%d", inp.query, TOP_K)
        results_iter = sc.search(
            search_text=inp.query or "",
            vector_queries=[
                VectorizedQuery(
                    vector=qvec,
                    k_nearest_neighbors=TOP_K,
                    fields="contentVector", 
                    # weight=1.0,  # optional boost
                )
            ],
            top=TOP_K,
            select=["id", "title", "page", "section_path", "content", "filepath"],
            logging_enable=True,
        )

        results = list(results_iter)  # force the request and materialize
        dt = (time.perf_counter() - t0) * 1000
        logger.info("AZSEARCH ok results=%d in %.1f ms", len(results), dt)

    except Exception as e:
        dt = (time.perf_counter() - t0) * 1000
        logger.exception("AZSEARCH failed after %.1f ms: %s", dt, e)
        raise

    # 4) Apply project filter if provided (post-processing)
    if project_filter:
        filtered_results = []
        for r in results:
            filepath = r.get("filepath", "")
            if filepath.startswith(project_filter):
                filtered_results.append(r)
        results = filtered_results
        logger.info("After project filtering: %d results remain", len(results))

    # 5) Map to your Hit model
    hits: List[Hit] = []
    for r in results:
        hits.append(Hit(
            id=r["id"],
            title=r.get("title", "") or "",
            page=int(r.get("page", 1) or 1),
            section_path=r.get("section_path", "") or "",
            snippet=_make_snippet(r.get("content", "") or "", inp.query),
            score=float(r.get("@search.score", 0.0) or 0.0),  # accessible without selecting it
        ))

    return SearchOutput(hits=hits)
