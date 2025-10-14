from typing import List

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient
from config import config
from tools.models import FetchInput, FetchOutput, Chunk

def _search_client() -> SearchClient:
    return SearchClient(
        config.ai_search.endpoint,
        config.ai_search.index_name,
        AzureKeyCredential(config.ai_search.api_key)
    )

def fetch_chunks(inp: FetchInput) -> FetchOutput:
    sc = _search_client()
    if not inp.ids:
        return FetchOutput(chunks=[])

    # Use search.in to batch by IDs
    quoted = ",".join([f"'{i}'" for i in inp.ids])
    flt = f"search.in(id, {quoted}, ',')"

    results = sc.search(
        search_text="*",
        filter=flt,
        top=len(inp.ids),
        select=["id","title","page","section_path","content","content_markdown"]
    )
    chunks: List[Chunk] = []
    for r in results:
        chunks.append(Chunk(
            id=r["id"],
            title=r.get("title","") or "",
            page=int(r.get("page",1) or 1),
            section_path=r.get("section_path","") or "",
            content=r.get("content","") or "",
            content_markdown=r.get("content_markdown")
        ))
    # keep original order roughly: sort by the order of inp.ids
    order = {k:i for i,k in enumerate(inp.ids)}
    chunks.sort(key=lambda c: order.get(c.id, 10**9))
    return FetchOutput(chunks=chunks)
