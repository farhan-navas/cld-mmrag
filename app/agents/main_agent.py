import logging, json
from typing import List, Optional, Dict, Any
from openai import AzureOpenAI

from app.tools.schema import OPENAI_TOOLS, TOOL_REGISTRY
from app.agents.query_rewrite_agent import run_query_rewrite_agent

from app.config import config

logger = logging.getLogger("main_agent")

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

Operational modes:
- Standard mode (default): search across the default RAG index.
- Costing mode: when instructed, serve only data from the cost-index corpus. Treat these answers as scoped to costing workflows, mention that context in your response, and avoid referencing non-cost sources. Tool routing is already handled for you—just remember the audience and keep content cost-specific.
- Access control: If the user is **not** in costing mode, you must refuse any request that is primarily about costing/budget/pricing data. Politely explain the restriction and invite them to contact a costing team member if they need that information.

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

def run_agent(
    query: str,
    message_history: Optional[List[Dict[str, str]]] = None,
    *,
    is_cost_team_member: bool = False,
) -> Dict[str, Any]:
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
    logger.info(
        "[START] run_agent query=%r is_cost_team_member=%s",
        query,
        is_cost_team_member,
    )

    target_index = (
        config.ai_search.cost_index_name
        if is_cost_team_member
        else config.ai_search.index_name
    )
    
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

    dynamic_prompt = SYSTEM_PROMPT + (
        "\nSPECIAL MODE ACTIVE: The user is a costing team member. All searches are already scoped to the cost index—keep answers focused on costing workflows and note this context explicitly."
        if is_cost_team_member
        else "\nRESTRICTION: The user is not cleared for costing data. If they ask about costing/budget/pricing specifics, decline and explain that only cost team members may access that information."
    )

    messages = [
        {"role": "system", "content": dynamic_prompt},
        {"role": "user", "content": optimized_query},  # Use optimized query
    ]

    while True:
        response = client.chat.completions.create(
            model=config.openai.deployment_name,   # Azure deployment name
            messages=messages,
            tools=OPENAI_TOOLS, # pyright: ignore[reportArgumentType]
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
            name = tc.function.name # pyright: ignore[reportAttributeAccessIssue]
            args = {}
            try:
                args = json.loads(tc.function.arguments or "{}") # pyright: ignore[reportAttributeAccessIssue]
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
            if name in {"search_docs", "fetch_chunks"}:
                args["index_name"] = target_index

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
