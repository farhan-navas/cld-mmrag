import os
import logging
import logging.config
from dataclasses import dataclass
from typing import Literal
from dotenv import load_dotenv

load_dotenv()

def _ensure_logs_dir(path: str):
    d = os.path.dirname(path) or "."
    os.makedirs(d, exist_ok=True)

def setup_logging():
    level = os.getenv("LOG_LEVEL", "INFO").upper()
    log_file = os.getenv("LOG_FILE", "logs/app.log")
    max_bytes = int(os.getenv("LOG_MAX_BYTES", "10000000"))  # 10 MB
    backups = int(os.getenv("LOG_BACKUP_COUNT", "5"))
    console_on = os.getenv("LOG_TO_CONSOLE", "1") not in ("0", "false", "False")
    enable_azure_http = os.getenv("ENABLE_AZURE_HTTP_LOGS", "0") in ("1", "true", "True")

    _ensure_logs_dir(log_file)

    handlers = {
        "file": {
            "class": "logging.handlers.RotatingFileHandler",
            "filename": log_file,
            "maxBytes": max_bytes,
            "backupCount": backups,
            "level": level,
            "formatter": "std",
        }
    }
    root_handlers = ["file"]

    if console_on:
        handlers["console"] = {
            "class": "logging.StreamHandler",
            "level": level,
            "formatter": "std",
        }
        root_handlers.append("console")

    LOG_CFG = {
        "version": 1,
        "disable_existing_loggers": False,
        "formatters": {
            "std": {"format": "%(asctime)s %(levelname)s [%(name)s] %(message)s"},
        },
        "handlers": handlers,
        "loggers": {
            # Named loggers
            "agent": {"handlers": root_handlers, "level": level, "propagate": False},
            "schema": {"handlers": root_handlers, "level": level, "propagate": False},
            "config": {"handlers": root_handlers, "level": level, "propagate": False},
            "tool.search_docs": {"handlers": root_handlers, "level": level, "propagate": False},
            "tool.synthesize_answers": {"handlers": root_handlers, "level": level, "propagate": False},
            "tool.fetch_chunks": {"handlers": root_handlers, "level": level, "propagate": False},
            "tool.math_eval": {"handlers": root_handlers, "level": level, "propagate": False},
            "tool.table_qa": {"handlers": root_handlers, "level": level, "propagate": False},

            # Azure SDK logs (file only by default)
            "azure": {"handlers": root_handlers, "level": "WARNING", "propagate": False},
            "azure.core.pipeline.policies.http_logging_policy": {
                "handlers": root_handlers,
                "level": "WARNING",
                "propagate": False,
            },
            # uvicorn (optional)
            "uvicorn": {"handlers": root_handlers, "level": "INFO", "propagate": False},
            "uvicorn.error": {"handlers": root_handlers, "level": "INFO", "propagate": False},
            "uvicorn.access": {"handlers": root_handlers, "level": "INFO", "propagate": False},
        },
        "root": {"handlers": root_handlers, "level": level},
    }

    logging.config.dictConfig(LOG_CFG)

    if enable_azure_http:
        logging.getLogger("azure").setLevel("INFO")
        logging.getLogger("azure.core.pipeline.policies.http_logging_policy").setLevel("INFO")

# init logging early
setup_logging()
_logger = logging.getLogger("config")

def _fingerprint(secret: str) -> str:
    if not secret:
        return ""
    return f"{secret[:4]}...{secret[-4:]}"

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
    deployment_name: str = "gpt4o"
    embedding_model: str = "text-embedding-3-small"
    api_version: str = "2024-05-01-preview"

@dataclass
class ModelConfig:
    """Configuration for vision models."""
    model_choice: Literal["florence2", "phi3-vision"] = "florence2"
    device: str = "cuda" if os.environ.get("CUDA_AVAILABLE") else "cpu"
    batch_size: int = 1

@dataclass
class SystemConfig:
    temp_dir: str = "./temp"
    patch_matrix_dir: str = "./patch_matrices"
    manifest_dir: str = "./manifests"
    max_pages_per_doc: int = 100
    default_k: int = 10

@dataclass
class IndexingConfig:
    chunk_max_chars: int = 2200
    chunk_overlap_chars: int = 220
    embed_batch_size: int = 64
    upload_batch_size: int = 500
    include_tables: bool = True
    supported_exts: tuple[str, ...] = (".pdf", ".docx", ".pptx", ".png", ".jpg", ".jpeg", ".tif", ".tiff", ".bmp", ".xlsx", ".csv")
    
    xlsx_rows_per_chunk: int = 100
    xlsx_cols_per_group: int = 12
    pptx_include_notes: bool = True

@dataclass
class SharePointConfig:
    ms_graph_api_endpoint: str
    credentials_url: str = ""  
    credentials_data: str = ""  
    faq_filename: str = "" # Optional

class Config:
    """Central configuration manager."""
    def __init__(self):
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
            deployment_name=os.getenv("AZURE_OPENAI_MODEL", "gpt4o")
        )

        self.indexing = IndexingConfig()

        self.sharepoint = SharePointConfig(
            ms_graph_api_endpoint=os.getenv("MS_GRAPH_API_ENDPOINT", ""),
            credentials_url=os.getenv("CREDENTIALS_URL", ""),
            credentials_data=os.getenv("CREDENTIALS_DATA", ""),
            faq_filename=os.getenv("FAQ_FILENAME", "")
        )

        model_choice_env = os.getenv("MODEL_CHOICE", "florence2")
        model_choice: Literal["florence2", "phi3-vision"] = (
            "florence2" if model_choice_env not in ["florence2", "phi3-vision"] else model_choice_env
        ) # type: ignore
        self.model = ModelConfig(model_choice=model_choice)
        self.system = SystemConfig()

    def validate(self) -> bool:
        required_fields = [
            (self.ai_search.endpoint, "AZURE_SEARCH_ENDPOINT"),
            (self.ai_search.api_key, "AZURE_SEARCH_API_KEY"),
            (self.doc_intelligence.endpoint, "AZURE_DOC_INTELLIGENCE_ENDPOINT"),
            (self.doc_intelligence.api_key, "AZURE_DOC_INTELLIGENCE_API_KEY"),
            (self.openai.endpoint, "AZURE_OPENAI_ENDPOINT"),
            (self.openai.api_key, "AZURE_OPENAI_API_KEY"),
        ]
        missing = [name for value, name in required_fields if not value]
        if missing:
            _logger.error("Missing required environment variables: %s", ", ".join(missing))
            return False
        _logger.info("Config validated OK")
        return True

# Global configuration instance (ensure logging is already set up above)
config = Config()
