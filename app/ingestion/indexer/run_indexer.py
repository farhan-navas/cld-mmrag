"""
Main entry point for the indexing pipeline.

This script orchestrates the entire indexing workflow:
1. Load and validate configuration
2. Ensure search index exists
3. Scan data directory for supported files
4. Route each file to appropriate extraction & chunking strategy
5. Embed and upload chunks to Azure AI Search
"""

import logging
from pathlib import Path

from app.config import config
from app.ingestion.indexer.index_manager import ensure_index
from app.ingestion.indexer.utils import DATA_DIR
from app.ingestion.indexer.chunking.strategies import route_profile
from app.ingestion.indexer import extract_blocks
from app.ingestion.indexer.chunking.text_splitter import split_fenced_code_blocks
from app.ingestion.indexer.chunking.pdf_chunker import chunk_blocks
from app.ingestion.indexer.chunking.excel_chunker import chunk_xlsx
from app.ingestion.indexer.chunking.pptx_chunker import chunk_pptx
from app.ingestion.indexer.uploader import upsert_chunks

logger = logging.getLogger("indexer.main")


def main():
    """Main indexing pipeline orchestration."""
    if config.validate():
        print("Nice! Config validated!")
    else:
        raise SystemExit("Missing required env vars.")
    
    ensure_index()
    
    print("CWD:", Path.cwd())
    print("DATA_DIR (given):", DATA_DIR, "exists?", DATA_DIR.exists())
    print("DATA_DIR absolute:", DATA_DIR.resolve())
    
    all_chunks = []
    supported = getattr(config.indexing, "supported_exts")
    for path in DATA_DIR.rglob("*"):
        print("Path here is", path)
        if not path.is_file() or path.suffix.lower() not in supported:
            continue
        print(f"\n[FILE] {path.name}")
        try:
            # Store relative path from data/preprocessed
            relative_path = str(path.relative_to(DATA_DIR))
            filepath_str = f"data/preprocessed/{relative_path}"
            
            # Route to appropriate chunking strategy based on file type
            profile = route_profile(path)
            
            if profile == "xlsx":
                print(f"  - Using Excel chunking strategy")
                chunks = chunk_xlsx(path, title=path.stem, filepath=filepath_str)
            elif profile == "pptx":
                print(f"  - Using PowerPoint chunking strategy")
                chunks = chunk_pptx(path, title=path.stem, filepath=filepath_str)
            else:
                # Current DI path (pdf/docx/images)
                print(f"  - Using Document Intelligence/Markitdown chunking strategy")
                blocks = extract_blocks(path)
                print(f"  - blocks: {len(blocks)}")
                if len(blocks) < 1:
                    print("  ! No blocks extracted (DI may have returned empty). Skipping.")
                    continue
                
                blocks = split_fenced_code_blocks(blocks)
                chunks = chunk_blocks(blocks, title=path.stem, filepath=filepath_str)
            
            print(f"  - chunks: {len(chunks)}")
            if not chunks:
                print("  ! No chunks produced. Skipping.")
                continue
            all_chunks.extend(chunks)
        except Exception as e:
            print(f"  !! Processing failed: {e}")
            logger.warning(f"Failed to process {path.name}: {e}", exc_info=True)
    
    if not all_chunks:
        print("\nNo chunks to upload. Check that your files are readable and DI returns content.")
        return
    
    # 3) Embed + upload
    print(f"\n[UPLOAD] Embedding and uploading {len(all_chunks)} chunks…")
    upsert_chunks(all_chunks)
    print("[DONE] Indexing complete.")


if __name__ == "__main__":
    main()
