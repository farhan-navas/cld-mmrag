import logging, json
from typing import List, Optional, Dict, Any, Callable
from openai import AzureOpenAI, AsyncAzureOpenAI

from tools.schema import OPENAI_TOOLS, TOOL_REGISTRY
from agents.query_rewrite_agent import run_query_rewrite_agent

from config import config

logger = logging.getLogger("agent")

DEPLOYMENT = config.openai.deployment_name
client = AzureOpenAI(
    api_key=config.openai.api_key,
    api_version=config.openai.api_version,
    azure_endpoint=config.openai.endpoint,
    azure_deployment=DEPLOYMENT
)

SYSTEM_PROMPT = """
You are an agent that answers user questions using the provided tools and your own reasoning.

Tool selection:
- Use `search_docs` then `fetch_chunks` when you need evidence from the corpus. Don’t invent sources.
- If the query asks for analytics over a Markdown table (avg/sum/min/max/trend/per/by), call `table_qa` on the first clearly relevant table.
- Only use `math_eval` for pure math expressions; otherwise do not use it.
- Minimize tool calls—only what’s needed for a high-quality answer.

Citations:
- If you used corpus content, include up to 3 citations in the final result (Title and page or section_path).
- If no corpus used, omit citations.

Answer style:
- Start with the direct answer, then brief reasoning or steps.
- If something is missing/ambiguous, state the gap and propose one concrete follow-up.

Reliability:
- Never fabricate tool outputs or citations.
- Don’t expose raw tool payloads unless asked.
- If a tool errors, report it briefly and proceed if possible.

Finish condition (IMPORTANT)
- When you are ready to finalize, you MUST call the `finalize_answer` function exactly once with the final JSON:
  { "answer": string, "citations": [ {id,title,page,section_path}... ]?, "follow_up"?: string }
- Never output extra text after calling `finalize_answer`.
"""

def run_agent(query: str, message_history: Optional[List[Dict[str, str]]] = None) -> Dict[str, Any]:
    """
    Core agent loop:
    0) Optionally rewrite query using query rewrite sub-agent (if multi-turn)
    1) Ask model what to do with tools
    2) Execute any tool calls
    3) Submit tool outputs
    4) Repeat until status=completed
    
    Args:
        query: The user's current query
        message_history: Optional list of prior conversation messages
    """
    logger.info("[START] run_agent query=%r", query)
    
    # STEP 0: Query Rewrite (if we have conversation history)
    optimized_query = query
    if message_history and len(message_history) > 1:
        logger.info("[AGENT] Spawning query rewrite sub-agent")
        rewrite_result = run_query_rewrite_agent(
            messages=message_history,
            current_query=query
        )
        optimized_query = rewrite_result["rewritten_query"]
        if rewrite_result["is_changed"]:
            logger.info("[AGENT] Query rewritten: %r → %r", query, optimized_query)
        else:
            logger.info("[AGENT] Query unchanged: %r", query)
    else:
        logger.info("[AGENT] Skipping query rewrite - no conversation history")

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": optimized_query},  # Use optimized query
    ]

    while True:
        response = client.chat.completions.create(
            model=config.openai.deployment_name,   # Azure deployment name
            messages=messages,
            tools=OPENAI_TOOLS,
            tool_choice="auto",
            temperature=0.1,
        )

        msg = response.choices[0].message
        tool_calls = msg.tool_calls or []

        if not tool_calls:
            # Model tried to finish without finalize; allow but return unstructured answer
            answer = (msg.content or "").strip() or "(no answer)"
            return {
                "answer": answer,
                "citations": getattr(msg, "citations", None),
                "follow_up": getattr(msg, "follow_up", None),
            }
        
        # Keep the assistant turn that requested tools
        messages.append({
            "role": "assistant",
            "content": msg.content,  # often None when tool_calls exist
            "tool_calls": [tc.model_dump() for tc in tool_calls],
        })

        for tc in tool_calls:
            name = tc.function.name
            args = {}
            try:
                args = json.loads(tc.function.arguments or "{}")
            except Exception:
                pass

            if name == "finalize_answer":
                # THIS means we are at the end of the conversation
                answer = args.get("answer", "") or "(no answer)"
                citations = args.get("citations")
                follow_up = args.get("follow_up")

                logger.info("RETURNING NOW!")
                return {
                    "answer": answer,
                    "citations": citations,
                    "follow_up": follow_up,
                }

            # Otherwise: execute normal tools and append a tool message
            try:
                out = TOOL_REGISTRY.get(name, lambda a: {"error": f"unknown tool {name}"})(args)
            except Exception as e:
                logger.exception("Tool %s failed", name)
                out = {"error": f"{type(e).__name__}: {e}"}

            messages.append({
                "role": "tool",
                "tool_call_id": tc.id,
                "name": name,
                "content": json.dumps(out),  # string content for Chat Completions
            })
