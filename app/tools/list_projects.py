from typing import Set, Optional
import logging

from azure.core.credentials import AzureKeyCredential
from azure.search.documents import SearchClient

from app.config import config
from app.tools.models import ListProjectsOutput, ProjectInfo

logger = logging.getLogger("tool.list_projects")


def _derive_project_name(filepath: str) -> Optional[str]:
    """Infer a project name from common filepath layouts."""
    if not filepath:
        return None

    parts = [p for p in filepath.split("/") if p]
    if not parts:
        return None

    # SharePoint layout: sharepoint/<folder path...>
    if parts[0] == "sharepoint":
        sharepoint_parts = parts[1:]
        if not sharepoint_parts:
            return None

        # Skip the standard "Shared Documents" prefix if present
        if sharepoint_parts[0].lower() == "shared documents" and len(sharepoint_parts) > 1:
            return sharepoint_parts[1]
        return sharepoint_parts[0]

    return None

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
            filepath = r.get("filepath", "") or ""
            project_name = _derive_project_name(filepath)
            if not project_name:
                continue

            projects.add(project_name)

            if project_name not in project_details:
                project_details[project_name] = {
                    "doc_count": 0,
                    "sample_files": []
                }

            project_details[project_name]["doc_count"] += 1

            if len(project_details[project_name]["sample_files"]) < 3:
                sample_file = filepath.split("/")[-1]
                if sample_file:
                    project_details[project_name]["sample_files"].append(sample_file)
        
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
