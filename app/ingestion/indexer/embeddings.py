"""
Embedding operations using Azure OpenAI.

This module handles text embedding generation for vector search.
"""

import logging
from typing import List

from app.config import config
from app.ingestion.indexer.clients import aoai_client

logger = logging.getLogger("indexer.embeddings")


def get_embedding(texts: List[str]) -> List[List[float]]:
    """
    Generate embeddings for a list of texts using Azure OpenAI.
    
    :param texts: List of text strings to embed
    :return: List of embedding vectors
    """
    logger.info(f"[START] embedding {len(texts)} texts")
    client = aoai_client()
    resp = client.embeddings.create(
        input=texts,
        model=config.openai.embedding_model
    )
    
    return [d.embedding for d in resp.data]


def embedding_dimension() -> int:
    """
    Get the dimension of the embedding model.
    
    :return: Number of dimensions in embedding vector
    """
    return len(get_embedding(["dim probe"])[0])
