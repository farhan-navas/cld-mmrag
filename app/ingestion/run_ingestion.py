import sys
import logging
from pathlib import Path

from app.ingestion.ingestion_incremental_load import SharePointIncrementalIngestion
from app.config import config

logger = logging.getLogger("run-ingestion")

# Configuration (for regular ingestion)
SHAREPOINT_FOLDER = "/External Data/(CLD) AI Projects/PDDM-Index"
MAPPING_FILE = Path("app/sharepoint-mapping-table-24-11.xlsx")  # local excel mapping table

# Configuration (for COST DATA ingestion)
# SHAREPOINT_FOLDER = "/External Data/(CLD) AI Projects/Cost-Index"
# MAPPING_FILE = Path("app/sharepoint-cost-mapping-table.xlsx") # local mapping table -> COST DATA

def run_ingestion():
    logger.info("=" * 60)
    logger.info("Starting SharePoint Incremental Ingestion")
    logger.info("=" * 60)
    
    # Validate config
    if not config.validate():
        logger.error("Configuration validation failed!")
        return False
    
    try:
        with SharePointIncrementalIngestion(config, logger) as ingestion:
            ingestion.run_incremental_ingestion(
                sharepoint_folder_path=SHAREPOINT_FOLDER,
                mapping_file_path=MAPPING_FILE
            )
            logger.info("=" * 60)
            logger.info("Ingestion completed successfully!")
            logger.info("=" * 60)
            return True
            
    except Exception as e:
        logger.error("=" * 60)
        logger.error(f"Ingestion failed: {e}", exc_info=True)
        logger.error("=" * 60)
        return False


if __name__ == "__main__":
    success = run_ingestion()
    sys.exit(0 if success else 1)
