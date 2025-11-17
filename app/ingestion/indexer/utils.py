"""
Shared utility functions and constants for the indexer.
"""

import os
import hashlib
from pathlib import Path

# Project root - going up from app/ingestion/indexer/ to repo root
PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Allow override via env, else default to <repo>/data/preprocessed
DATA_DIR = Path(os.getenv("DATA_DIR", PROJECT_ROOT / "data" / "preprocessed")).resolve()


def sha1(s: str) -> str:
    """
    Generate SHA1 hash for a string.
    
    :param s: String to hash
    :return: SHA1 hash as hex string
    """
    return hashlib.sha1(s.encode("utf-8")).hexdigest()


def stable_id(filepath: str, content: str) -> str:
    """
    Generate stable ID for a chunk based on filepath and content.
    
    :param filepath: Path to the source file
    :param content: Chunk content
    :return: SHA1 hash as hex string
    """
    return hashlib.sha1((filepath + "\n" + content).encode("utf-8")).hexdigest()
