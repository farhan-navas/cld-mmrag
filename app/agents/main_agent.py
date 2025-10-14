from typing import List, Optional

from tools.models import SearchInput, FetchInput, Chunk, TableQAInput, MathInput
from tools.search_docs import search_docs
from tools.fetch_chunks import fetch_chunks
from tools.table_qa import table_qa
from tools.math_eval import math_eval
from tools.synthesize import synthesize_answer

def answer_with_agent(query: str):
    # fast math shortcut if user gives a pure expression
    print("[START]: ANSWER WITH AGENT")

    if all(ch in "0123456789.+-*/()% " for ch in query.strip()) and any(ch in "+-*/%" for ch in query):
        print("[START]: math eval")
        m = math_eval(MathInput(expression=query))
        print("[END]: math eval")
        return {
            "answer": str(m.result),
            "citations": [],
            "follow_up": None
        }

    # 1) Retrieve
    print("[START]: search docs")
    hits = search_docs(SearchInput(query=query, top_k=8)).hits
    print("[END]: search docs")
    if not hits:
        return {
            "answer": "I couldn’t find evidence for that in your corpus.",
            "citations": [],
            "follow_up": "Try different keywords or upload more relevant files (PDF/DOCX/PPTX)."
        }

    # 2) Fetch full chunks for top hits
    top_ids = [h.id for h in hits[:5]]
    chunks: List[Chunk] = fetch_chunks(FetchInput(ids=top_ids)).chunks

    # 3) Decide on table_qa
    table_note: Optional[str] = None
    tabley = any(k in query.lower() for k in ["per ", " by ", "trend", "average", "sum", "max", "min"])
    if tabley:
        for c in chunks:
            if c.content_markdown and c.content_markdown.strip().startswith("|"):
                tqa = table_qa(TableQAInput(markdown=c.content_markdown, question=query))
                table_note = tqa.short_answer
                break

    # 4) Synthesize answer
    answer = synthesize_answer(query, chunks, table_note=table_note)

    # Build citations (top 3)
    citations = [{"id": c.id, "title": c.title, "page": c.page, "section_path": c.section_path} for c in chunks[:3]]
    return {
        "answer": answer,
        "citations": citations,
        "follow_up": "Want me to narrow to a specific document or date range?"
    }
