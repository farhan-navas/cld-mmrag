import os
import logging
import tempfile
import pandas as pd
from pathlib import Path

from app.ingestion.indexer import search_client, ensure_index
from app.ingestion import sharepoint_api, mapping_table, doc_processor
from app.ingestion.utils import sha1

class SharePointIncrementalIngestion:
    """
    Handles incremental ingestion from SharePoint using indexer.py backend.
    
    Workflow:
    1. Fetch current SharePoint file list
    2. Load previous mapping table from Excel
    3. Compare to detect new/modified/deleted files
    4. Delete chunks for deleted/modified files
    5. Process and upload new/modified files
    6. Update mapping table
    """
    
    def __init__(self, config, logger=None):
        """
        Initialize the ingestion orchestrator.
        
        :param config: Configuration object with Azure service credentials
        :param logger: Optional logger instance
        """
        self.config = config
        self.logger = logger or logging.getLogger("ingestion_incremental_load")
        self.search_client = search_client()
        self.temp_dir = None
        
    def __enter__(self):
        """Create temporary directory for downloaded files."""
        self.temp_dir = tempfile.mkdtemp(prefix="sharepoint_ingestion_")
        self.logger.info(f"Created temp directory: {self.temp_dir}")
        return self
        
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Clean up temporary directory."""
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
            self.logger.info(f"Cleaned up temp directory: {self.temp_dir}")
    
    def download_sharepoint_file(self, download_url: str, filename: str) -> Path:
        """
        Download a file from SharePoint to temporary directory.
        
        :param download_url: The @microsoft.graph.downloadUrl from file metadata
        :param filename: Name of the file
        :return: Path to the downloaded file
        """
        if not self.temp_dir:
            raise RuntimeError("Temporary directory not initialized")
        
        local_path = Path(self.temp_dir) / filename
        
        try:
            sharepoint_api.download_file(download_url, local_path)
            self.logger.info(f"Downloaded {filename} to {local_path}")
            return local_path
            
        except Exception as e:
            self.logger.error(f"Failed to download {filename}: {e}")
            raise
    
    def run_incremental_ingestion(
        self,
        sharepoint_folder_path: str,
        mapping_file_path: Path
    ) -> None:
        """
        Main orchestration function for incremental ingestion from SharePoint.
        
        :param sharepoint_folder_path: Path to SharePoint folder (e.g., "Shared Documents/YourFolder")
        :param mapping_file_path: Path to Excel file for tracking state (e.g., Path("data/mapping.xlsx"))
        """
        self.logger.info("=" * 80)
        self.logger.info("Starting SharePoint Incremental Ingestion")
        self.logger.info("=" * 80)
        
        # Ensure Azure AI Search index exists
        ensure_index()
        
        # Step 1: Get current SharePoint file list
        self.logger.info("\n[1] Fetching current SharePoint file list...")
        self.logger.info(f"Fetching file list from SharePoint: {sharepoint_folder_path}")
        
        current_mapping = sharepoint_api.create_mapping_table(sharepoint_folder_path, self.config)
        
        if current_mapping.empty:
            self.logger.error("No files found in SharePoint folder!")
            raise ValueError(f"No files found in SharePoint folder: {sharepoint_folder_path}")
        
        self.logger.info(f"Found {len(current_mapping)} files in SharePoint")
        
        # Step 2: Get previous mapping table from Excel
        self.logger.info(f"\n[2] Retrieving previous mapping table from {mapping_file_path}...")
        previous_mapping = mapping_table.load_mapping_table(mapping_file_path)
        
        # Step 3: Compare to detect changes
        self.logger.info("\n[3] Comparing mappings to detect changes...")
        comparison = mapping_table.compare_mapping_tables(previous_mapping, current_mapping)
        
        if comparison['status'] == 'no_change':
            self.logger.info("✓ No changes detected. Ingestion complete.")
            return
        
        modified_df = comparison['modified']
        deleted_df = comparison['deleted']
        inserted_df = comparison['inserted']
        
        self.logger.info(f"  - Modified files: {len(modified_df)}")
        self.logger.info(f"  - Deleted files: {len(deleted_df)}")
        self.logger.info(f"  - New files: {len(inserted_df)}")
        
        # Step 4: Handle deletions
        if not deleted_df.empty:
            self.logger.info("\n[4] Handling deleted files...")
            deleted_filepaths = deleted_df['Filename'].tolist()
            doc_keys_to_delete = [sha1(f"sharepoint/{fp}") for fp in deleted_filepaths]
            doc_processor.delete_by_doc_keys(doc_keys_to_delete, self.search_client)
        
        # Step 5: Handle modifications (delete old chunks, then re-process)
        if not modified_df.empty:
            self.logger.info("\n[5] Handling modified files...")
            modified_filepaths = modified_df['Filename'].tolist()
            doc_keys_to_delete = [sha1(f"sharepoint/{fp}") for fp in modified_filepaths]
            doc_processor.delete_by_doc_keys(doc_keys_to_delete, self.search_client)
        
        # Step 6: Process new and modified files
        files_to_process = pd.concat([modified_df, inserted_df], ignore_index=True)
        
        if not files_to_process.empty:
            self.logger.info(f"\n[6] Processing {len(files_to_process)} files...")
            
            all_chunks = []
            for idx, row in files_to_process.iterrows():
                filename = row['Filename']
                download_url = row.get('DownloadUrl')
                
                if not download_url:
                    self.logger.warning(f"No download URL for {filename}, skipping...")
                    continue
                
                # Download file from SharePoint
                local_file_path = self.download_sharepoint_file(download_url, filename)
                
                # Process file through indexer.py pipeline
                sharepoint_relative_path = f"sharepoint/{row.get('FolderPath', '')}/{filename}"
                chunks = doc_processor.process_file_to_chunks(local_file_path, sharepoint_relative_path)
                
                all_chunks.extend(chunks)
            
            # Embed and upload all chunks
            if all_chunks:
                self.logger.info(f"\n[7] Embedding and uploading {len(all_chunks)} chunks...")
                
                # Get batch sizes from config
                embed_batch_size = getattr(self.config.indexing, "embed_batch_size", 100)
                upload_batch_size = getattr(self.config.indexing, "upload_batch_size", 100)
                
                # Embed chunks
                chunks_with_embeddings = doc_processor.embed_chunks(all_chunks, embed_batch_size)
                
                # Prepare documents with IDs and doc_keys
                docs = doc_processor.prepare_documents_for_upload(chunks_with_embeddings)
                
                # Upload to Azure AI Search
                doc_processor.upload_to_search(docs, self.search_client, upload_batch_size)
            else:
                self.logger.warning("No chunks produced from processed files")
        
        # Step 8: Update mapping table in Excel
        self.logger.info(f"\n[8] Updating mapping table to {mapping_file_path}...")
        mapping_table.save_mapping_table(mapping_file_path, current_mapping)
        
        self.logger.info("\n" + "=" * 80)
        self.logger.info("✓ SharePoint Incremental Ingestion Complete")
        self.logger.info("=" * 80)
