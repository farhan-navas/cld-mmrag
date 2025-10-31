import json
import logging
import requests
import pandas as pd
from typing import List, Dict, Any, Optional
from pathlib import Path

logger = logging.getLogger("sharepoint_api")

def get_auth_token(config) -> Dict[str, Any]:
    """
    Get authentication token for Microsoft Graph API.
    
    :param config: Configuration object with sharepoint.credentials_url
    :return: Dictionary with 'auth_token' key containing Bearer token
    """
    function_url = config.sharepoint.credentials_url
    
    headers = {'Content-Type': "application/x-www-form-urlencoded"}
    response = requests.post(function_url, headers=headers)
    
    if response.status_code == 200:
        res = json.loads(response.text)
        logger.info("Microsoft Account Graph Access Token Retrieval Successful")
        return {'auth_token': res}
    else:
        logger.error(f"Microsoft Account Graph Access Token Retrieval Failed: {response.text}")
        return None # pyright: ignore[reportReturnType]


def unpack_requests_response(url: str, authorization_token: str) -> List[Dict[str, Any]]:
    """
    Make request to Microsoft Graph API and return files/folders.
    
    :param url: The Graph API URL
    :param authorization_token: Bearer token for authentication
    :return: List of file/folder objects from Graph API
    """
    headers = {
        'Authorization': f'{authorization_token}',
        'Content-Type': 'application/json'
    }
    
    response = requests.get(url, headers=headers)
    response.raise_for_status()
    
    data = response.json()
    return data.get('value', [])


def get_sharepoint_files(folder_path: str, config, authorization_token: Optional[str] = None) -> List[Dict[str, Any]]:
    """
    Recursively get all files from SharePoint folder using Microsoft Graph API.
    
    :param folder_path: Path to SharePoint folder
    :param config: Configuration object
    :param authorization_token: Optional auth token (will be generated if not provided)
    :return: List of file dictionaries with metadata
    """
    logger.info(f"Getting files from {folder_path}")
    
    if not authorization_token:
        auth_token_full = get_auth_token(config)
        authorization_token = auth_token_full['auth_token']  # pyright: ignore[reportOptionalSubscript]
    
    # Construct Graph API URL
    url = f"https://graph.microsoft.com/v1.0/sites/cl.sharepoint.com,7e4f27f4-f93b-4a06-be07-0b5fe6cae129,34925334-c72e-43be-9384-7ebe8d561b6a/drives/b!9CdPfjv5Bkq-Bwtf5srhKTRTkjQux75Dk4R-vo1WG2p4WeQHkaDfQpA2zAqlG70g/root:{folder_path}:/children"
    url = url.replace(" ", "%20")
    
    results = unpack_requests_response(url, authorization_token)  # pyright: ignore[reportArgumentType]
    final_results = results.copy()
    
    for f in results:
        if 'folder' in list(f.keys()):
            # It's a folder - recurse into it
            folder_name = f['name']
            sub_folder_path = folder_path + '/' + folder_name
            final_results = final_results + get_sharepoint_files(sub_folder_path, config, authorization_token)
        else:
            # It's a file - add folder path metadata
            f['folder_path'] = folder_path
    
    return final_results


def create_mapping_table(folder_path: str, config) -> pd.DataFrame:
    """
    Create mapping table of SharePoint files with metadata.
    Filters to only include PDFs and optionally FAQ Excel files.
    
    :param folder_path: Path to SharePoint folder
    :param config: Configuration object with sharepoint.faq_filename
    :return: DataFrame with columns: Filename, Url, LastModified, DownloadUrl, FolderPath
    """
    faq_filename = config.sharepoint.faq_filename
    documents = get_sharepoint_files(folder_path, config)
    
    # Only accept PDF and Excel files
    required_file_mimetypes = [
        'application/pdf',
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
    ]
    
    mapping_table_data = []
    
    for f in documents:
        if 'file' in list(f.keys()):
            mimetype = f.get('file', {}).get('mimeType')
            
            if mimetype in required_file_mimetypes:
                # Special handling for Excel files - only accept FAQ file
                if mimetype == 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet':
                    if faq_filename and faq_filename in f.get('name'):
                        f_dict = {
                            'Filename': f.get('name'),
                            'Url': f.get('webUrl'),
                            'LastModified': f.get('lastModifiedDateTime'),
                            'DownloadUrl': f.get('@microsoft.graph.downloadUrl'),
                            'FolderPath': f.get('folder_path')
                        }
                        mapping_table_data.append(f_dict)
                    else:
                        logger.debug(f"Excel file {f.get('name')} is different from config faq_filename {faq_filename}. Skipping")
                else:
                    # PDF or other accepted file types
                    f_dict = {
                        'Filename': f.get('name'),
                        'Url': f.get('webUrl'),
                        'LastModified': f.get('lastModifiedDateTime'),
                        'DownloadUrl': f.get('@microsoft.graph.downloadUrl'),
                        'FolderPath': f.get('folder_path')
                    }
                    mapping_table_data.append(f_dict)
    
    return pd.DataFrame(mapping_table_data)


def download_file(download_url: str, local_path: Path) -> None:
    """
    Download a file from SharePoint using Microsoft Graph API download URL.
    
    :param download_url: The @microsoft.graph.downloadUrl from file metadata
    :param local_path: Local path to save the downloaded file
    :raises: requests.HTTPError if download fails
    """
    response = requests.get(download_url, stream=True)
    response.raise_for_status()
    
    with open(local_path, 'wb') as f:
        for chunk in response.iter_content(chunk_size=8192):
            f.write(chunk)
    
    logger.info(f"Downloaded file to {local_path}")
