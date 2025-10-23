"""
THIS FILE MIGHT BE USELESS NOW!!!!
"""
import logging, time

from typing import List, Dict, Any
from openai import AzureOpenAI
from openai.types.chat import ChatCompletionMessageParam

from config import config

logger = logging.getLogger("tool.query_rewrite")

def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=config.openai.api_key,
        api_version=config.openai.api_version,
        azure_endpoint=config.openai.endpoint,
    )


REWRITE_SYSTEM_PROMPT = """
You are a query optimization expert for a document search system.
Your task: Transform conversational queries into optimized standalone search queries.

Guidelines:
1. Resolve pronouns and references using conversation history
2. Extract key entities, dates, numbers, and technical terms
3. Make the query self-contained (no references to "it", "that", "the previous")
4. Preserve important specifics (dates, names, metrics, locations)
5. Remove conversational filler ("um", "like", "you know")
6. If the original query is already clear and standalone, return it unchanged

Examples:

History: "What is the completion percentage for foundation works?"
Current: "What about substructure?"
Rewritten: "What is the completion percentage for substructure works?"

History: "Show me the SPRINT Plot 1 project status"
Current: "When is it expected to complete?"
Rewritten: "When is the SPRINT Plot 1 project expected to complete?"

Current: "What is the total budget for Building 1B?"
Rewritten: "What is the total budget for Building 1B?"

Respond with ONLY the rewritten query, nothing else."""


def query_rewrite(
    messages: List[Dict[str, str]],
    current_query: str
) -> Dict[str, Any]:
    client = _client()

    t0 = time.perf_counter()
    logger.info("query_rewrite start query=%r history_msgs=%d", current_query, len(messages))
    
    # If no history or very first message, return as-is
    if not messages or len(messages) <= 1:
        logger.info("query_rewrite skip - first message, no history")
        return {
            "rewritten_query": current_query,
            "reasoning": "First message - no rewrite needed"
        }
    
    client = _client()
    
    # Build context from last 6 messages (3 exchanges) to keep token count reasonable
    recent_messages = messages[-6:]
    context_parts = []
    
    for msg in recent_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            context_parts.append(f"User: {content}")
        elif role == "assistant":
            # Truncate assistant responses to save tokens
            truncated = content[:200] + "..." if len(content) > 200 else content
            context_parts.append(f"Assistant: {truncated}")
    
    conversation_context = "\n".join(context_parts)
    
    logger.debug("query_rewrite context_msgs=%d context_chars=%d", 
                 len(recent_messages), len(conversation_context))
    
    # Prepare messages for rewrite LLM call
    rewrite_messages: List[ChatCompletionMessageParam] = [
        {"role": "system", "content": REWRITE_SYSTEM_PROMPT},
        {"role": "user", "content": f"""Conversation History:
{conversation_context}

Current Query: {current_query}

Rewritten Query:"""}
    ]
    
    try:
        t1 = time.perf_counter()
        resp = client.chat.completions.create(
            model=config.openai.deployment_name,
            temperature=0.1,
            max_tokens=150,
            messages=rewrite_messages,
        )
        llm_time = (time.perf_counter() - t1) * 1000
        
        rewritten = resp.choices[0].message.content or current_query
        rewritten = rewritten.strip()
        
        # Validation - if rewrite is empty or too short, use original
        if not rewritten or len(rewritten) < 3:
            logger.warning("query_rewrite validation_failed - empty/short result")
            return {
                "rewritten_query": current_query,
                "reasoning": "Rewrite failed validation - using original query"
            }
        
        # Check if query was actually changed
        reasoning = None
        changed = rewritten.lower().strip() != current_query.lower().strip()
        
        if not changed:
            reasoning = "Query already optimal - no changes needed"
            logger.info("query_rewrite unchanged in %.1f ms (llm=%.1f ms)", 
                       (time.perf_counter() - t0) * 1000, llm_time)
        else:
            reasoning = f"Rewritten for context: '{current_query}' → '{rewritten}'"
            logger.info("query_rewrite ok rewritten_len=%d in %.1f ms (llm=%.1f ms)", 
                       len(rewritten), (time.perf_counter() - t0) * 1000, llm_time)
        
        return {
            "rewritten_query": rewritten,
            "reasoning": reasoning
        }
        
    except Exception as e:
        # Fallback to original query on any error
        logger.exception("query_rewrite failed after %.1f ms: %s", 
                        (time.perf_counter() - t0) * 1000, e)
        return {
            "rewritten_query": current_query,
            "reasoning": f"Error during rewrite: {str(e)}"
        }