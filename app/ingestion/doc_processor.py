import logging
from pathlib import Path
from typing import List, Dict, Any

from app.ingestion.indexer import extract_blocks_with_di, chunk_blocks, split_fenced_code_blocks, get_embedding
from app.ingestion.utils import sha1, stable_id


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
        # Step 1: Extract blocks with Azure Document Intelligence
        blocks = extract_blocks_with_di(file_path)
        logger.info(f"  - Extracted {len(blocks)} blocks")
        
        if len(blocks) < 1:
            logger.warning(f"  ! No blocks extracted from {file_path.name}")
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


def embed_chunks(chunks: List[Dict[str, Any]], batch_size: int = 100) -> List[Dict[str, Any]]:
    """
    Add embeddings to chunks using Azure OpenAI.
    
    :param chunks: List of chunk dictionaries from chunk_blocks()
    :param batch_size: Number of chunks to embed at once
    :return: List of chunks with 'contentVector' added
    """
    if not chunks:
        return []
    
    logger.info(f"Embedding {len(chunks)} chunks...")
    
    for i in range(0, len(chunks), batch_size):
        batch = chunks[i:i+batch_size]
        # Truncate content to 8000 chars for embedding
        texts = [ch["content"][:8000] for ch in batch]
        vectors = get_embedding(texts)
        
        for ch, v in zip(batch, vectors):
            ch["contentVector"] = v
        
        logger.info(f"  - Embedded batch {i//batch_size + 1}")
    
    return chunks


def prepare_documents_for_upload(chunks: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Prepare chunks for upload by adding IDs and doc_keys.
    Groups chunks by filepath and assigns stable IDs.
    
    :param chunks: List of chunk dictionaries with embeddings
    :return: List of documents ready for Azure AI Search upload
    """
    if not chunks:
        return []
    
    # Group chunks by file for doc_key assignment
    by_file = {}
    for ch in chunks:
        filepath = ch["filepath"]
        if filepath not in by_file:
            by_file[filepath] = []
        by_file[filepath].append(ch)
    
    docs = []
    
    for filepath, file_chunks in by_file.items():
        doc_key = sha1(filepath)
        
        # Assign stable IDs and doc_key to each chunk
        for idx, ch in enumerate(file_chunks):
            doc_id = stable_id(filepath, ch["content"])
            docs.append({
                "id": doc_id,
                "doc_key": doc_key,
                "chunk_index": idx,
                **ch
            })
    
    return docs


def upload_to_search(
    docs: List[Dict[str, Any]],
    search_client,
    batch_size: int = 100
) -> None:
    """
    Upload documents to Azure AI Search in batches.
    
    :param docs: List of documents with embeddings and IDs
    :param search_client: Azure Search client instance
    :param batch_size: Number of documents to upload at once
    """
    if not docs:
        return
    
    logger.info(f"Uploading {len(docs)} documents to Azure AI Search...")
    
    for i in range(0, len(docs), batch_size):
        batch = docs[i:i+batch_size]
        search_client.upload_documents(batch)
        logger.info(f"  - Uploaded batch {i//batch_size + 1}")


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
