from typing import List, Set
import logging

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

from app.config import config
from app.tools.models import ListProjectsOutput, ProjectInfo

logger = logging.getLogger("tool.list_projects")

def _search_client() -> SearchClient:
    return SearchClient(
        endpoint=config.ai_search.endpoint,
        index_name=config.ai_search.index_name,
        credential=AzureKeyCredential(config.ai_search.api_key),
    )

def list_projects() -> ListProjectsOutput:
    sc = _search_client()
    
    try:
        logger.info("Fetching all documents to extract project names")
        
        # Query all documents, select only filepath
        results_iter = sc.search(
            search_text="*",  # Match all documents
            select=["filepath", "title"],
            top=1000,  # Adjust based on expected corpus size
        )
        
        results = list(results_iter)
        logger.info(f"Retrieved {len(results)} documents from index")
        
        # Extract unique project names from filepaths
        projects: Set[str] = set()
        project_details: dict = {}  # project_name -> {doc_count, sample_files}
        
        for r in results:
            filepath = r.get("filepath", "")
            if not filepath:
                continue
            
            # Parse: data/preprocessed/{project_name}/...
            parts = filepath.split("/")
            if len(parts) >= 3 and parts[0] == "data" and parts[1] == "preprocessed":
                project_name = parts[2]
                projects.add(project_name)
                
                # Track project details
                if project_name not in project_details:
                    project_details[project_name] = {
                        "doc_count": 0,
                        "sample_files": []
                    }
                
                project_details[project_name]["doc_count"] += 1
                
                # Keep sample filenames (max 3)
                if len(project_details[project_name]["sample_files"]) < 3:
                    filename = parts[-1] if len(parts) > 3 else ""
                    if filename:
                        project_details[project_name]["sample_files"].append(filename)
        
        # Build ProjectInfo objects
        project_list = []
        for proj in sorted(projects):
            details = project_details.get(proj, {})
            project_list.append(
                ProjectInfo(
                    name=proj,
                    doc_count=details.get("doc_count", 0),
                    sample_files=details.get("sample_files", [])
                )
            )
        
        logger.info(f"Found {len(project_list)} unique projects: {[p.name for p in project_list]}")
        
        return ListProjectsOutput(projects=project_list)
        
    except Exception as e:
        logger.exception("Failed to list projects: %s", e)
        # Return empty list on error
        return ListProjectsOutput(projects=[])
