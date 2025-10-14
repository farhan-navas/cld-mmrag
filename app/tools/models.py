from pydantic import BaseModel
from typing import List, Optional

class SearchInput(BaseModel):
    query: str
    top_k: int = 8
    filter: Optional[str] = None  # Azure Search OData filter

class Hit(BaseModel):
    id: str
    title: str
    page: int
    section_path: str
    snippet: str
    score: float

class SearchOutput(BaseModel):
    hits: List[Hit]

class FetchInput(BaseModel):
    ids: List[str]

class Chunk(BaseModel):
    id: str
    title: str
    page: int
    section_path: str
    content: str
    content_markdown: Optional[str] = None

class FetchOutput(BaseModel):
    chunks: List[Chunk]

class TableQAInput(BaseModel):
    markdown: str
    question: str

class TableQAOutput(BaseModel):
    short_answer: str
    analysis: str

class MathInput(BaseModel):
    expression: str

class MathOutput(BaseModel):
    result: float

class Citation(BaseModel):
    id: str
    title: str
    page: int
    section_path: str

class AskResponse(BaseModel):
    answer: str
    citations: List[Citation]
    follow_up: str | None = None
