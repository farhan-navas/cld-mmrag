"""
Query Rewrite Agent - Specialist agent for optimizing user queries.
This agent analyzes conversation history and rewrites queries for better search results.
"""
import logging
import time
from typing import List, Dict, Any
from openai import AzureOpenAI
from openai.types.chat import ChatCompletionMessageParam

from config import config

logger = logging.getLogger("agent.query_rewrite")


def _client() -> AzureOpenAI:
    return AzureOpenAI(
        api_key=config.openai.api_key,
        api_version=config.openai.api_version,
        azure_endpoint=config.openai.endpoint,
    )


QUERY_REWRITE_SYSTEM_PROMPT = """You are a query optimization specialist for a document search system.

Your ONLY task: Transform conversational queries into optimized standalone search queries.

Guidelines:
1. Resolve ALL pronouns and references using conversation history
   - Replace "it", "that", "the previous", "this", "them" with actual entities
2. Extract and preserve key entities, dates, numbers, technical terms
3. Make the query completely self-contained and searchable
4. Preserve important specifics (dates, names, metrics, locations, project names)
5. Remove conversational filler ("um", "like", "you know", "can you", "please")
6. If the original query is already clear and standalone, return it unchanged
7. Focus on SEARCH optimization - think about what keywords would match documents

Examples:

Conversation:
User: "What is the completion percentage for foundation works?"
Assistant: "The foundation works are 85% complete as of..."
User: "What about substructure?"

Your output: "What is the completion percentage for substructure works?"

---

Conversation:
User: "Show me the SPRINT Plot 1 project status"
Assistant: "SPRINT Plot 1 is currently in progress..."
User: "When is it expected to complete?"

Your output: "When is SPRINT Plot 1 project expected to complete?"

---

Conversation:
User: "What is the total budget for Building 1B?"

Your output: "What is the total budget for Building 1B?"

CRITICAL: Respond with ONLY the rewritten query, nothing else. No explanations, no preamble."""


def run_query_rewrite_agent(
    messages: List[Dict[str, str]],
    current_query: str
) -> Dict[str, Any]:
    """
    Runs the query rewrite agent to optimize a user query based on conversation history.
    
    Args:
        messages: List of conversation messages with 'role' and 'content' keys
        current_query: The current user query to optimize
        
    Returns:
        Dict with:
            - rewritten_query (str): The optimized search query
            - reasoning (str): Explanation of what was done
            - is_changed (bool): Whether the query was actually modified
    """
    t0 = time.perf_counter()
    logger.info("query_rewrite_agent start query=%r history_msgs=%d", 
                current_query, len(messages))
    
    # If no history or very first message, return as-is
    if not messages or len(messages) <= 1:
        logger.info("query_rewrite_agent skip - first message, no history")
        return {
            "rewritten_query": current_query,
            "reasoning": "First message - no rewrite needed",
            "is_changed": False
        }
    
    client = _client()
    
    # Build context from last 6 messages (3 exchanges) to keep token count reasonable
    recent_messages = messages[-6:]
    
    # Build conversation context for the agent
    agent_messages: List[ChatCompletionMessageParam] = [
        {"role": "system", "content": QUERY_REWRITE_SYSTEM_PROMPT}
    ]
    
    # Add conversation history
    for msg in recent_messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        if role == "user":
            agent_messages.append({"role": "user", "content": content})
        elif role == "assistant":
            # Truncate assistant responses to save tokens
            if len(content) > 300:
                content = content[:300] + "..."
            agent_messages.append({"role": "assistant", "content": content})
    
    # Add the current query as the final user message
    agent_messages.append({
        "role": "user", 
        "content": f"Current query to optimize: {current_query}"
    })
    
    logger.debug("query_rewrite_agent context_msgs=%d agent_msgs=%d", 
                 len(recent_messages), len(agent_messages))
    
    try:
        t1 = time.perf_counter()
        response = client.chat.completions.create(
            model=config.openai.deployment_name,
            temperature=0.1,  # Low temperature for consistent, deterministic rewrites
            max_tokens=150,
            messages=agent_messages,
        )
        llm_time = (time.perf_counter() - t1) * 1000
        
        rewritten = response.choices[0].message.content or current_query
        rewritten = rewritten.strip()
        
        # Remove any quotes that the model might have added
        if rewritten.startswith('"') and rewritten.endswith('"'):
            rewritten = rewritten[1:-1]
        if rewritten.startswith("'") and rewritten.endswith("'"):
            rewritten = rewritten[1:-1]
        
        # Validation - if rewrite is empty or too short, use original
        if not rewritten or len(rewritten) < 3:
            logger.warning("query_rewrite_agent validation_failed - empty/short result")
            return {
                "rewritten_query": current_query,
                "reasoning": "Rewrite validation failed - using original",
                "is_changed": False
            }
        
        # Check if query was actually changed
        is_changed = rewritten.lower().strip() != current_query.lower().strip()
        
        if not is_changed:
            reasoning = "Query already optimal - no changes needed"
            logger.info("query_rewrite_agent unchanged in %.1f ms (llm=%.1f ms)", 
                       (time.perf_counter() - t0) * 1000, llm_time)
        else:
            reasoning = f"Optimized for search: '{current_query}' → '{rewritten}'"
            logger.info("query_rewrite_agent ok rewritten_len=%d changed=True in %.1f ms (llm=%.1f ms)", 
                       len(rewritten), (time.perf_counter() - t0) * 1000, llm_time)
        
        return {
            "rewritten_query": rewritten,
            "reasoning": reasoning,
            "is_changed": is_changed
        }
        
    except Exception as e:
        # Fallback to original query on any error
        logger.exception("query_rewrite_agent failed after %.1f ms: %s", 
                        (time.perf_counter() - t0) * 1000, e)
        return {
            "rewritten_query": current_query,
            "reasoning": f"Error during rewrite: {str(e)}",
            "is_changed": False
        }
