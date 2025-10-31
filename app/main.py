import time
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List, Optional
from app.tools.models import AskResponse
from app.agents.main_agent import run_agent

from fastapi.responses import JSONResponse

app = FastAPI()

class Message(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class AskRequest(BaseModel):
    query: str
    message_history: Optional[List[Message]] = None

@app.get("/")
def read_root():
    return JSONResponse(content={"Hello": "World"}, status_code=200)

@app.post("/ask", response_model=AskResponse)
def ask(req: AskRequest):
    t0 = time.time()
    
    # Convert Pydantic models to dicts for internal use
    history = [msg.model_dump() for msg in req.message_history] if req.message_history else None
    
    out = run_agent(req.query, message_history=history)
    
    print(f"THIS TOOK {time.time() - t0} YEARS TO RUN !!!!!!!!!!!!!!!!!!!!!!!!")
    return AskResponse(**out)

@app.get("/health")
def health():
    return JSONResponse(content={ "status": "ok" }, status_code=200)
