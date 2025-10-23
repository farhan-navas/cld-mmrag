from typing import List, Dict, Any, Optional, Callable
from pydantic import BaseModel, Field

from tools.models import SearchInput, SearchOutput, Chunk, Hit, FetchInput, FetchOutput, TableQAInput, TableQAOutput, MathInput, MathOutput
from tools.search_docs import search_docs
from tools.fetch_chunks import fetch_chunks
from tools.table_qa import table_qa
from tools.math_eval import math_eval

# TOOL FUNCTION OUTPUT SCHEMA
class SearchSchema(BaseModel):
    query: str = Field(..., description="Search query string.")
    top_k: int = Field(8, ge=1, le=50, description="Max results to retrieve.")

class FetchSchema(BaseModel):
    ids: List[str] = Field(..., description="Document or chunk IDs to fetch.")

class TableQASchema(BaseModel):
    markdown: str = Field(..., description="A Markdown table.")
    question: str = Field(..., description="A natural language question over the table.")

class MathSchema(BaseModel):
    expression: str = Field(..., description="A pure math expression to evaluate, e.g. '12*(3+4)%5'.")


def _tool_search_docs(args: Dict[str, Any]) -> Dict[str, Any]:
    a = SearchSchema(**args)
    res = search_docs(SearchInput(query=a.query))
    out = SearchOutput(
        hits=[
            Hit(
                id=h.id,
                title=getattr(h, "title", None),
                page=getattr(h, "page", None),
                section_path=getattr(h, "section_path", None),
                snippet=getattr(h, "snippet", None),
                score=getattr(h, "score", None),
            )
            for h in res.hits
        ]
    )
    return out.model_dump()

def _tool_fetch_chunks(args: Dict[str, Any]) -> Dict[str, Any]:
    a = FetchSchema(**args)
    res = fetch_chunks(FetchInput(ids=a.ids))
    out = FetchOutput(
        chunks=[
            Chunk(
                id=c.id,
                doc_key=c.doc_key,
                chunk_index=c.chunk_index,
                title=getattr(c, "title", None),
                page=getattr(c, "page", None),
                section_path=getattr(c, "section_path", None),
                content=(getattr(c, "content", None) or None),
                content_markdown=((c.content_markdown or "")[:50_000] if getattr(c, "content_markdown", None) else None),
            )
            for c in res.chunks
        ]
    )
    return out.model_dump()

def _tool_table_qa(args: Dict[str, Any]) -> Dict[str, Any]:
    a = TableQASchema(**args)
    res = table_qa(TableQAInput(markdown=a.markdown, question=a.question))
    out = TableQAOutput(short_answer=res.short_answer, explanation=getattr(res, "explanation", None))
    return out.model_dump()

def _tool_math_eval(args: Dict[str, Any]) -> Dict[str, Any]:
    a = MathSchema(**args)
    res = math_eval(MathInput(expression=a.expression))
    out = MathOutput(result=res.result)
    return out.model_dump()

TOOL_REGISTRY: Dict[str, Callable[[Dict[str, Any]], Dict[str, Any]]] = {
    "search_docs": _tool_search_docs,
    "fetch_chunks": _tool_fetch_chunks,
    "table_qa": _tool_table_qa,
    "math_eval": _tool_math_eval,
}

OPENAI_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "search_docs",
            "description": "Retrieve top-K relevant items for a query from the indexed corpus.",
            "parameters": SearchSchema.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fetch_chunks",
            "description": "Fetch full chunk contents by IDs returned from search_docs.",
            "parameters": FetchSchema.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "table_qa",
            "description": "Answer a question about a Markdown table.",
            "parameters": TableQASchema.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "math_eval",
            "description": "Safely evaluate a pure math expression.",
            "parameters": MathSchema.model_json_schema(),
        },
    },
    {
        "type": "function",
        "function": {
            "name": "finalize_answer",
            "description": "Submit the final answer in a fixed schema. Call this exactly once when you are ready to finish.",
            "parameters": {
                "type": "object",
                "properties": {
                    "answer": {"type": "string", "description": "Natural-language answer. Do not include citation blobs here."},
                    "citations": {
                        "type": "array",
                        "description": "Up to 3 supporting sources if corpus was used.",
                        "items": {
                            "type": "object",
                            "properties": {
                                "id": {"type": "string"},
                                "title": {"type": "string"},
                                "page": {"type": ["integer", "null"]},
                                "section_path": {"type": ["string", "null"]}
                            },
                            "required": ["id", "title"]
                        }
                    },
                    "follow_up": {"type": ["string", "null"], "description": "Optional single follow-up question to refine or continue."}
                },
                "required": ["answer"]
            }
        }
    }
]
