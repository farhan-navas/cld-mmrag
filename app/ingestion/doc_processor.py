import logging
from pathlib import Path
from typing import List, Dict, Any

from app.ingestion.indexer import extract_blocks, chunk_blocks, split_fenced_code_blocks

logger = logging.getLogger("doc_processor")

def process_file_to_chunks(
    file_path: Path,
    sharepoint_relative_path: str
) -> List[Dict[str, Any]]:
    """
    Process a single file using indexer.py pipeline.
    
    :param file_path: Local path to the downloaded file
    :param sharepoint_relative_path: Relative path in SharePoint (for metadata)
    :return: List of chunk dictionaries ready for upload
    """
    logger.info(f"Processing file: {file_path.name}")
    
    try:
        # Step 1: Extract blocks using configured extractor
        blocks = extract_blocks(file_path)
        logger.info(f"  - Extracted {len(blocks)} blocks")
        
        if len(blocks) < 1:
            logger.warning(f"! No blocks extracted from {file_path.name}")
            return []
        
        # Step 2: Split fenced code blocks
        blocks = split_fenced_code_blocks(blocks)
        
        # Step 3: Chunk the blocks intelligently
        chunks = chunk_blocks(
            blocks,
            title=file_path.stem,
            filepath=sharepoint_relative_path
        )
        logger.info(f"  - Created {len(chunks)} chunks")
        
        if not chunks:
            logger.warning(f"! No chunks produced from {file_path.name}")
            return []
        
        return chunks
        
    except Exception as e:
        logger.error(f"!! Failed to process {file_path.name}: {e}")
        return []
def delete_by_doc_keys(doc_keys: List[str], search_client) -> None:
    """
    Delete all chunks belonging to specific documents from Azure AI Search.
    
    :param doc_keys: List of doc_key values (SHA1 hashes of filepaths)
    :param search_client: Azure Search client instance
    """
    if not doc_keys:
        return
    
    logger.info(f"Deleting chunks for {len(doc_keys)} documents...")
    
    for doc_key in doc_keys:
        # Search for all chunks with this doc_key
        filter_expr = f"doc_key eq '{doc_key}'"
        results = search_client.search(
            search_text="*",
            filter=filter_expr,
            select=["id"],
            top=1000  # Adjust if you have more chunks per doc
        )
        
        chunk_ids = [{"id": doc["id"]} for doc in results]
        
        if chunk_ids:
            search_client.delete_documents(chunk_ids)
            logger.info(f"  - Deleted {len(chunk_ids)} chunks for doc_key {doc_key[:8]}...")
