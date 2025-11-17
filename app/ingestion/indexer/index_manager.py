"""
Azure AI Search index management.

This module handles index creation and schema definition.
"""

import logging
from azure.search.documents.indexes.models import (
    SearchIndex, SearchField, SearchFieldDataType,
    SimpleField, SearchableField, VectorSearch, HnswAlgorithmConfiguration,
    VectorSearchProfile, HnswParameters, SearchSuggester
)

from app.config import config
from app.ingestion.indexer.clients import search_index_client
from app.ingestion.indexer.embeddings import embedding_dimension

logger = logging.getLogger("indexer.index_manager")


def ensure_index() -> None:
    """
    Create Azure AI Search index if it doesn't exist.
    Defines the schema with vector search configuration.
    """
    sic = search_index_client()
    idx_name = config.ai_search.index_name
    
    try:
        sic.get_index(idx_name)
        print(f"Index '{idx_name}' exists.")
        return
    except Exception:
        pass
    
    dims = embedding_dimension()
    
    hnsw = HnswAlgorithmConfiguration(
        name="hnsw",
        parameters=HnswParameters(m=16, ef_construction=400, ef_search=100)
    )
    vs = VectorSearch(
        algorithms=[hnsw],
        profiles=[VectorSearchProfile(name="default", algorithm_configuration_name="hnsw")]
    )
    fields = [
        SimpleField(name="id", type=SearchFieldDataType.String, key=True),
        SimpleField(name="doc_key", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SimpleField(name="chunk_index", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SearchableField(name="title", type=SearchFieldDataType.String, filterable=True, sortable=True),
        SearchableField(name="filepath", type=SearchFieldDataType.String, filterable=True),
        SimpleField(name="page", type=SearchFieldDataType.Int32, filterable=True, sortable=True),
        SearchableField(name="section_path", type=SearchFieldDataType.String, filterable=True),
        SearchableField(name="content", type=SearchFieldDataType.String),
        SearchableField(name="content_markdown", type=SearchFieldDataType.String),
        # vector field
        SearchField(
            name="contentVector",
            type=SearchFieldDataType.Collection(SearchFieldDataType.Single),
            searchable=True,
            vector_search_dimensions=dims,
            vector_search_profile_name="default",
        ),
        SearchableField(name="bbox", type=SearchFieldDataType.String),
        SearchableField(name="metadata_json", type=SearchFieldDataType.String),
    ]
    index = SearchIndex(
        name=idx_name,
        fields=fields,
        vector_search=vs,
        suggesters=[SearchSuggester(name="sg", source_fields=["title", "content"])]
    )
    sic.create_index(index)
    print(f"Created index '{idx_name}'.")
