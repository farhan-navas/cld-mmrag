import logging, json
from typing import List, Optional, Dict, Any, Callable
from openai import AzureOpenAI, AsyncAzureOpenAI

from app.tools.schema import OPENAI_TOOLS, TOOL_REGISTRY
from app.agents.query_rewrite_agent import run_query_rewrite_agent

from app.config import config

logger = logging.getLogger("agent")

DEPLOYMENT = config.openai.deployment_name
client = AzureOpenAI(
    api_key=config.openai.api_key,
    api_version=config.openai.api_version,
    azure_endpoint=config.openai.endpoint,
    azure_deployment=DEPLOYMENT
)

SYSTEM_PROMPT = """
You are the CapitaLand Development Project Domain Knowledge Agent, designed to assist internal CapitaLand users with questions about their projects.

Your Knowledge Base:
- The document corpus contains information about multiple CapitaLand development projects.
- Each project has its own set of documents organized by filepath (e.g., data/preprocessed/project_name/documents).
- Documents include technical specifications, reports, plans, and project-related materials.
- When searching, pay attention to the filepath and title to identify which project the information comes from.
- Users may be asking about specific projects, so always cite the source project/document clearly.

Handling Ambiguous Queries:
- If the user's question is ambiguous and could apply to multiple projects, FIRST call `list_projects` to see what projects exist.
- Present the available projects to the user and ask them to specify which one they're interested in.
- If the user mentions a project name that might not exist, call `list_projects` to validate it before searching.
- If a search returns results from multiple projects, present the information organized by project and ask if they want details on a specific one.
- Only search broadly if the user explicitly asks to compare or see information across all projects.

Tool selection:
- Use `list_projects` when you need to validate a project name or show available projects to the user.
- Use `search_docs` with the `project_name` parameter when searching within a specific project (e.g., search_docs(query="...", project_name="25.PDDM Resource")).
- Use `search_docs` without `project_name` to search across all projects.
- After `search_docs`, use `fetch_chunks` to get full content for relevant results.
- If the query asks for analytics over a Markdown table (avg/sum/min/max/trend/per/by), call `table_qa` on the first clearly relevant table.
- Only use `math_eval` for pure math expressions; otherwise do not use it.
- Minimize tool calls—only what's needed for a high-quality answer.

Citations:
- If you used corpus content, include up to 3 citations in the final result (Title, page or section_path, and filepath when relevant to distinguish projects).
- Always indicate which project the information comes from if multiple projects exist in the corpus.
- If no corpus used, omit citations.

Answer style:
- Start with the direct answer, then brief reasoning or steps.
- If information spans multiple projects, clearly distinguish which information comes from which project.
- If something is missing/ambiguous, state the gap and propose one concrete follow-up.

Reliability:
- Never fabricate tool outputs or citations.
- Don't expose raw tool payloads unless asked.
- If a tool errors, report it briefly and proceed if possible.
- Never assume a project exists without checking `list_projects` first.

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
