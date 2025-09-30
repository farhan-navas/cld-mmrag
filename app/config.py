"""
Configuration module for MS-Native Late Interaction RAG system.

Contains all Azure service configurations, model choices, and system settings.
"""

import os
from dataclasses import dataclass
from typing import Literal 
from dotenv import load_dotenv

load_dotenv()

# @dataclass
# class AzureBlobConfig:
#     """Configuration for Azure Blob Storage."""
#     account_name: str
#     account_key: str
#     container_name: str = "rag-documents"


@dataclass
class AzureAISearchConfig:
    """Configuration for Azure AI Search."""
    endpoint: str
    api_key: str
    index_name: str = "rag-index"


@dataclass 
class AzureDocIntelligenceConfig:
    """Configuration for Azure Document Intelligence."""
    endpoint: str
    api_key: str


@dataclass
class AzureOpenAIConfig:
    """Configuration for Azure OpenAI."""
    endpoint: str
    api_key: str
    deployment_name: str = "gpt-4o"
    api_version: str = "2024-02-01"


@dataclass
class ModelConfig:
    """Configuration for vision models."""
    model_choice: Literal["florence2", "phi3-vision"] = "florence2"
    device: str = "cuda" if os.environ.get("CUDA_AVAILABLE") else "cpu"
    batch_size: int = 1


@dataclass
class SystemConfig:
    """System-wide configuration."""
    temp_dir: str = "./temp"
    patch_matrix_dir: str = "./patch_matrices"
    manifest_dir: str = "./manifests"
    max_pages_per_doc: int = 100
    default_k: int = 10


class Config:
    """Central configuration manager."""
    
    def __init__(self):
        # self.blob = AzureBlobConfig(
        #     account_name=os.getenv("AZURE_STORAGE_ACCOUNT_NAME", ""),
        #     account_key=os.getenv("AZURE_STORAGE_ACCOUNT_KEY", "")
        # )
        
        self.ai_search = AzureAISearchConfig(
            endpoint=os.getenv("AZURE_SEARCH_ENDPOINT", ""),
            api_key=os.getenv("AZURE_SEARCH_API_KEY", "")
        )
        
        self.doc_intelligence = AzureDocIntelligenceConfig(
            endpoint=os.getenv("AZURE_DOC_INTELLIGENCE_ENDPOINT", ""),
            api_key=os.getenv("AZURE_DOC_INTELLIGENCE_API_KEY", "")
        )
        
        self.openai = AzureOpenAIConfig(
            endpoint=os.getenv("AZURE_OPENAI_ENDPOINT", ""),
            api_key=os.getenv("AZURE_OPENAI_API_KEY", ""),
            deployment_name=os.getenv("AZURE_OPENAI_MODEL", "o4-mini")
        )
        
        model_choice_env = os.getenv("MODEL_CHOICE", "florence2")
        model_choice: Literal["florence2", "phi3-vision"] = "florence2" if model_choice_env not in ["florence2", "phi3-vision"] else model_choice_env  # pyright: ignore[reportAssignmentType]
        self.model = ModelConfig(
            model_choice=model_choice
        )
        
        self.system = SystemConfig()
    
    def validate(self) -> bool:
        required_fields = [
            # (self.blob.account_name, "AZURE_STORAGE_ACCOUNT_NAME"),
            # (self.blob.account_key, "AZURE_STORAGE_ACCOUNT_KEY"),
            (self.ai_search.endpoint, "AZURE_SEARCH_ENDPOINT"),
            (self.ai_search.api_key, "AZURE_SEARCH_API_KEY"),
            (self.doc_intelligence.endpoint, "AZURE_DOC_INTELLIGENCE_ENDPOINT"),
            (self.doc_intelligence.api_key, "AZURE_DOC_INTELLIGENCE_API_KEY"),
            (self.openai.endpoint, "AZURE_OPENAI_ENDPOINT"),
            (self.openai.api_key, "AZURE_OPENAI_API_KEY"),
        ]
        
        missing_fields = []

        for value, field_name in required_fields:
            if not value:
                missing_fields.append(field_name)
        
        if missing_fields:
            print(f"Missing required environment variables: {', '.join(missing_fields)}")
            return False
        
        return True


# Global configuration instance
config = Config()