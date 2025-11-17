"""
Azure service client factories.

This module provides factory functions for creating Azure SDK clients
used throughout the indexing pipeline.
"""

import logging
from azure.core.credentials import AzureKeyCredential
from azure.search.documents.indexes import SearchIndexClient
from azure.search.documents import SearchClient
from azure.ai.documentintelligence import DocumentIntelligenceClient
from openai import AzureOpenAI

from app.config import config

logger = logging.getLogger("indexer.clients")

def search_index_client() -> SearchIndexClient:
    """
    Create Azure AI Search Index client for index management operations.
    
    :return: SearchIndexClient instance
    """
    return SearchIndexClient(
        config.ai_search.endpoint,
        AzureKeyCredential(config.ai_search.api_key)
    )


def search_client() -> SearchClient:
    """
    Create Azure AI Search client for document operations.
    
    :return: SearchClient instance
    """
    return SearchClient(
        config.ai_search.endpoint,
        config.ai_search.index_name,
        AzureKeyCredential(config.ai_search.api_key)
    )


def di_client() -> DocumentIntelligenceClient:
    """
    Create Azure Document Intelligence client for document analysis.
    
    :return: DocumentIntelligenceClient instance
    """
    return DocumentIntelligenceClient(
        config.doc_intelligence.endpoint,
        AzureKeyCredential(config.doc_intelligence.api_key)
    )


def aoai_client() -> AzureOpenAI:
    """
    Create Azure OpenAI client for embeddings and completions.
    
    :return: AzureOpenAI instance
    """
    return AzureOpenAI(
        api_key=config.openai.api_key,
        api_version=config.openai.api_version,
        azure_endpoint=config.openai.endpoint,
    )
