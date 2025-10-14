from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from tools.models import AskResponse
from agents.main_agent import answer_with_agent  # implement per policy

app = FastAPI()

@app.get("/")
def read_root():
    return {"Hello": "World"}

@app.post("/ask", response_model=AskResponse)
def ask(req: str):
    out = answer_with_agent(req)
    return AskResponse(**out)
