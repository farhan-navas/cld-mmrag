from typing import List
import re

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from azure.search.documents.models import VectorizedQuery

from config import config
from tools.models import SearchInput, SearchOutput, Hit

from indexer import aoai_client, get_embedding

def _search_client() -> SearchClient:
    return SearchClient(
        config.ai_search.endpoint,
        config.ai_search.index_name,
        AzureKeyCredential(config.ai_search.api_key)
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
    sc = _search_client()

    # embed the query, hybrid
    qvec = get_embedding([inp.query])[0]
    print("here is the query vec", qvec[0:10])

    results = sc.search(
        search_text=inp.query or "*",
        vectors=[
            VectorizedQuery(
                vector=qvec,
                k_nearest_neighbors=inp.top_k,
                fields="contentVector",
                # weight=1.0,          # boost the vector part
            )
        ],
        top=inp.top_k,
        select=["id","title","page","section_path","content","@search.score"],
    )

    hits: List[Hit] = []
    for r in results:
        print(r.get("content"))
        hits.append(Hit(
            id=r["id"],
            title=r.get("title", "") or "",
            page=int(r.get("page", 1) or 1),
            section_path=r.get("section_path", "") or "",
            snippet=_make_snippet(r.get("content", "") or "", inp.query),
            score=float(r.get("@search.score", 0.0) or 0.0),
        ))

    return SearchOutput(hits=hits)
