from pydantic import BaseModel, Field
from typing import List, Optional, Dict

class SearchInput(BaseModel):
    query: str
    filter: Optional[str] = None

class Hit(BaseModel):
    id: str
    title: Optional[str] = None
    page: Optional[int] = None
    section_path: Optional[str] = None
    snippet: Optional[str] = None
    score: Optional[float] = None

class SearchOutput(BaseModel):
    hits: List[Hit]

class FetchInput(BaseModel):
    ids: List[str]

class Chunk(BaseModel):
    id: str
    doc_key: str
    chunk_index: int
    title: Optional[str] = None
    page: Optional[int] = None
    section_path: Optional[str] = None
    content: Optional[str] = None
    content_markdown: Optional[str] = None

class FetchOutput(BaseModel):
    chunks: List[Chunk]

class TableQAInput(BaseModel):
    markdown: str
    question: str

class TableQAOutput(BaseModel):
    short_answer: str
    explanation: Optional[str] = None

class MathInput(BaseModel):
    expression: str

class MathOutput(BaseModel):
    result: float

class QueryRewriteInput(BaseModel):
    messages: List[Dict[str, str]]
    current_query: str

class QueryRewriteOutput(BaseModel):
    rewritten_query: str
    reasoning: Optional[str] 

class Citation(BaseModel):
    id: str
    title: str
    page: Optional[int] = None
    section_path: Optional[str] = None

class AskResponse(BaseModel):
    answer: str
    citations: Optional[List[Citation]] = Field(..., description="used corpus during the request")
    follow_up: Optional[str] = None
