"""
THIS MIGHT NOW BE USELESS!?????
"""

import logging

from typing import List, Optional
from openai import AzureOpenAI
from openai.types.chat import ChatCompletionMessageParam

from config import config
from tools.models import Chunk

logger = logging.getLogger("tool.synthesize_answers")

def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=config.openai.api_key,
        api_version=config.openai.api_version,
        azure_endpoint=config.openai.endpoint,
    )

SYSTEM_PROMPT = """You are a grounded RAG assistant. 
Use ONLY the provided chunks to answer.
Cite like: [Title p.Page]. If unsure or no evidence, say so."""

def synthesize_answer(query: str, chunks: List[Chunk], table_note: Optional[str] = None) -> str:
    logger.info("synthesize start query=%r chunks=%d has_table_note=%s",
            query, len(chunks), table_note is not None)

    ctx = []
    for i, c in enumerate(chunks[:5]):
        ctx.append(
            f"[{i+1}] Title: {c.title} | Page: {c.page} | Section: {c.section_path}\n{c.content[:2000]}"
        )
    if table_note:
        ctx.append(f"[Table note] {table_note}")

    logger.debug("context_bullets=%d total_context_chars=%d",
             len(ctx), sum(len(x) for x in ctx))
    messages: List[ChatCompletionMessageParam] = [
        {"role":"system", "content": SYSTEM_PROMPT},
        {"role":"user", "content": f"Question: {query}\n\nSources:\n\n" + "\n\n".join(ctx)}
    ]
    client = _client()
    resp = client.chat.completions.create(
        model=config.openai.deployment_name,
        temperature=0.1,
        messages=messages,
    )

    ans = resp.choices[0].message.content or ""
    logger.info("synthesize ok answer_chars=%d", ans)
    return ans
