import logging
import pandas as pd
from pathlib import Path
from typing import Dict, Any

logger = logging.getLogger("mapping_table")

def load_mapping_table(mapping_file_path: Path) -> pd.DataFrame:
    """
    Load mapping table from Excel file.
    
    :param mapping_file_path: Path to the Excel mapping file
    :return: DataFrame with mapping table data, or empty DataFrame if file doesn't exist
    """
    if mapping_file_path.exists():
        try:
            df = pd.read_excel(mapping_file_path)
            logger.info(f"Loaded mapping table from {mapping_file_path} ({len(df)} entries)")
            return df
        except Exception as e:
            logger.error(f"Failed to read mapping table from {mapping_file_path}: {e}")
            return pd.DataFrame()
    else:
        logger.info(f"Mapping file {mapping_file_path} does not exist - starting fresh")
        return pd.DataFrame()


def save_mapping_table(mapping_file_path: Path, df: pd.DataFrame) -> None:
    """
    Save mapping table to Excel file.
    
    :param mapping_file_path: Path to save the Excel mapping file
    :param df: DataFrame to save
    :raises: Exception if save fails
    """
    try:
        # Ensure the directory exists
        mapping_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        # Save to Excel
        df.to_excel(mapping_file_path, index=False, engine='openpyxl')
        logger.info(f"Saved mapping table to {mapping_file_path} ({len(df)} entries)")
    except Exception as e:
        logger.error(f"Failed to save mapping table to {mapping_file_path}: {e}")
        raise


def compare_mapping_tables(
    previous_df: pd.DataFrame,
    current_df: pd.DataFrame
) -> Dict[str, Any]:
    """
    Compare previous and current mapping tables to detect changes.
    
    :param previous_df: Previous mapping table
    :param current_df: Current mapping table
    :return: Dictionary with:
        - 'status': 'no_change' or 'changes'
        - 'modified': DataFrame of modified files
        - 'deleted': DataFrame of deleted files
        - 'inserted': DataFrame of new files
    """
    if previous_df.empty and current_df.empty:
        return {
            'status': 'no_change',
            'modified': pd.DataFrame(),
            'deleted': pd.DataFrame(),
            'inserted': pd.DataFrame()
        }
    
    if previous_df.empty:
        return {
            'status': 'changes',
            'modified': pd.DataFrame(),
            'deleted': pd.DataFrame(),
            'inserted': current_df
        }
    
    # Compare based on Filename and LastModified
    prev_files = set(previous_df['Filename'])
    curr_files = set(current_df['Filename'])
    
    # New files
    new_files = curr_files - prev_files
    inserted_df = current_df[current_df['Filename'].isin(new_files)]
    
    # Deleted files
    deleted_files = prev_files - curr_files
    deleted_df = previous_df[previous_df['Filename'].isin(deleted_files)]
    
    # Modified files (same filename but different LastModified)
    common_files = prev_files & curr_files
    modified_list = []
    
    for filename in common_files:
        prev_row = previous_df[previous_df['Filename'] == filename].iloc[0]
        curr_row = current_df[current_df['Filename'] == filename].iloc[0]
        
        # Compare LastModified timestamp
        if prev_row['LastModified'] != curr_row['LastModified']:
            modified_list.append(curr_row)
    
    modified_df = pd.DataFrame(modified_list) if modified_list else pd.DataFrame()
    
    if inserted_df.empty and deleted_df.empty and modified_df.empty:
        return {
            'status': 'no_change',
            'modified': pd.DataFrame(),
            'deleted': pd.DataFrame(),
            'inserted': pd.DataFrame()
        }
    
    return {
        'status': 'changes',
        'modified': modified_df,
        'deleted': deleted_df,
        'inserted': inserted_df
    }
