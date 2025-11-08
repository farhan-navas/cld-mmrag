"""
Text splitting utilities.

This module provides functions for recursively splitting text while
preserving semantic boundaries and creating overlapping chunks.
"""

import logging
import re
from typing import List, Optional, Dict, Any

from app.config import config

logger = logging.getLogger("indexer.chunking.text_splitter")


def recursive_split_text(text: str, max_chars: int, separators: Optional[List[str]] = None) -> List[str]:
    """
    Recursively split text using a hierarchy of separators.
    
    Tries to split at semantic boundaries (paragraphs, sentences, etc.)
    before resorting to character-level splitting.
    
    :param text: Text to split
    :param max_chars: Maximum characters per chunk
    :param separators: Ordered list of separators (paragraph → sentence → word)
    :return: List of text chunks
    """
    if separators is None:
        # Default hierarchy: paragraph → sentence → clause → word
        separators = [
            "\n\n",      # Paragraph breaks
            "\n",        # Line breaks
            ". ",        # Sentences
            "! ",        # Exclamations
            "? ",        # Questions
            "; ",        # Clauses
            ", ",        # Phrases
            " ",         # Words
            ""           # Characters (last resort)
        ]
    
    # Base case: text fits in max_chars
    if len(text) <= max_chars:
        return [text] if text.strip() else []
    
    # Try each separator in order
    for i, sep in enumerate(separators):
        if sep == "":
            # Last resort: split by characters
            chunks = []
            for j in range(0, len(text), max_chars):
                chunks.append(text[j:j + max_chars])
            return chunks
        
        if sep in text:
            # Split by this separator
            splits = text.split(sep)
            
            # Reconstruct chunks respecting max_chars
            chunks = []
            current_chunk = ""
            
            for split in splits:
                # Re-add separator (except for last split)
                piece = split + sep if split != splits[-1] else split
                
                # If this single piece is too large, recurse with next separator
                if len(piece) > max_chars:
                    # Flush current chunk first
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                        current_chunk = ""
                    # Recurse on the large piece
                    sub_chunks = recursive_split_text(piece, max_chars, separators[i+1:])
                    chunks.extend(sub_chunks)
                    continue
                
                # If adding this piece would exceed max, flush current chunk
                if current_chunk and len(current_chunk) + len(piece) > max_chars:
                    chunks.append(current_chunk.strip())
                    current_chunk = piece
                else:
                    current_chunk += piece
            
            # Flush remaining
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            return chunks
    
    # Fallback (should never reach here)
    return [text]


def create_overlap_chunks(chunks: List[str], overlap_chars: int) -> List[str]:
    """
    Add overlapping context between consecutive chunks.
    
    Takes content from the end of the previous chunk and prepends it
    to the current chunk with a [...] marker.
    
    :param chunks: List of text chunks
    :param overlap_chars: Number of characters to overlap
    :return: List of chunks with overlap added
    """
    if not chunks or overlap_chars <= 0:
        return chunks
    
    out = [chunks[0]]
    for i in range(1, len(chunks)):
        prev_chunk, curr = chunks[i-1], chunks[i]
        overlap = prev_chunk[-overlap_chars:] if len(prev_chunk) > overlap_chars else prev_chunk
        
        # Start at a word boundary near the end of the overlap block
        # (prefer the last whitespace so we carry full words)
        cut = max(overlap.rfind(" "), 0)
        overlap = overlap[cut:].lstrip()
        
        # Ensure final length ≤ max_chars
        max_len = config.indexing.chunk_max_chars
        room = max_len - len(curr) - len(" [...] ")  # marker cost
        if room < 0:
            # curr itself is already at/over limit; keep it as-is
            out.append(curr)
            continue
        if len(overlap) > room:
            overlap = overlap[-room:]  # trim from the left
        
        out.append((overlap + " [...] " + curr) if overlap else curr)
    return out


def split_fenced_code_blocks(blocks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Split fenced code blocks (```) out of paragraph blocks.
    
    Separates code blocks into their own atomic chunks to prevent
    splitting code mid-syntax.
    
    :param blocks: List of block dictionaries
    :return: List of blocks with code blocks separated
    """
    FENCE_RE = re.compile(
        r"(?P<fence>```|~~~)(?P<lang>[^\n]*)\n(?P<body>.*?)(?:\n(?P=fence))",
        re.DOTALL
    )
    
    out = []
    for b in blocks:
        if b.get("type") != "paragraph":
            out.append(b)
            continue
        
        text = b.get("text") or ""
        pos = 0
        for m in FENCE_RE.finditer(text):
            start, end = m.span()
            # preface text before fence -> paragraph
            pre = text[pos:start].strip()
            if pre:
                out.append({**b, "text": pre, "markdown": pre, "type": "paragraph"})
            # fenced code -> codeblock
            code_lang = (m.group("lang") or "").strip()
            code_body = m.group("body")
            code_md = f"```{code_lang}\n{code_body}\n```"
            out.append({
                **b,
                "type": "codeblock",
                "text": code_md,
                "markdown": code_md,
            })
            pos = end
        # tail after last fence
        tail = text[pos:].strip()
        if tail:
            out.append({**b, "text": tail, "markdown": tail, "type": "paragraph"})
    return out
