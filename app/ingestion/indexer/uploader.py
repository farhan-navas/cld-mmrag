"""
Document upload operations to Azure AI Search.

This module handles chunk preparation, ID generation, and batch uploading.
"""

import logging
from typing import List, Dict, Any
from collections import defaultdict

from app.config import config
from app.ingestion.indexer.clients import search_client
from app.ingestion.indexer.embeddings import get_embedding
from app.ingestion.utils import sha1, stable_id

logger = logging.getLogger("indexer.uploader")

def upsert_chunks(chunks: List[Dict[str, Any]]) -> None:
    """
    Embed and upload chunks to Azure AI Search.
    
    Groups chunks by file, assigns stable IDs and doc_keys,
    generates embeddings, and uploads in batches.
    
    :param chunks: List of chunk dictionaries from chunking functions
    """
    sc = search_client()
    eb = config.indexing.embed_batch_size
    ub = config.indexing.upload_batch_size
    
    # Group chunks by file for doc_key assignment
    by_file = defaultdict(list)
    for ch in chunks:
        by_file[ch["filepath"]].append(ch)
    
    docs: List[Dict[str, Any]] = []
    for filepath, file_chunks in by_file.items():
        doc_key = sha1(filepath)
        
        for idx, ch in enumerate(file_chunks):
            doc_id = stable_id(filepath, ch["content"])
            docs.append({
                "id": doc_id,
                "doc_key": doc_key,  # groups chunks from the same doc
                "chunk_index": idx,  # gives us chunk pos in sequence
                **ch
            })
    
    # Embed in batches
    for i in range(0, len(docs), eb):
        batch = docs[i:i+eb]
        vectors = get_embedding([d["content"][:8000] for d in batch])
        for d, v in zip(batch, vectors):
            d["contentVector"] = v
        
        # Upload in sub-batches if needed
        for j in range(0, len(batch), ub):
            sub = batch[j:j+ub]
            sc.upload_documents(sub)
