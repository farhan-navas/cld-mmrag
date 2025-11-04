import logging
from typing import List, Dict, Any
from pathlib import Path
import pandas as pd

logger = logging.getLogger("indexer.extractors.excel")

def extract_excel_sheets(path: Path) -> List[Dict[str, Any]]:
    """
    extract sheets from excel file
    """
    try:
        xl = pd.ExcelFile(path)
    except Exception as e:
        logger.warning(f"Failed to load Excel file {path.name}: {e}")
        return []
    
    sheets = []
    for sheet_name in xl.sheet_names:
        try:
            df = xl.parse(sheet_name)
            # Clean column names
            df.columns = [str(c) for c in df.columns]
            sheets.append({
                "sheet_name": sheet_name,
                "dataframe": df
            })
        except Exception as e:
            logger.warning(f"Failed to parse sheet '{sheet_name}' in {path.name}: {e}")
            continue
    
    return sheets
