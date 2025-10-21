import time
from fastapi import FastAPI
from pydantic import BaseModel
from typing import List
from tools.models import AskResponse
from agents.main_agent import run_agent  # implement per policy

from fastapi.responses import JSONResponse

app = FastAPI()

@app.get("/")
def read_root():
    return JSONResponse(content={"Hello": "World"}, status_code=200)

@app.post("/ask", response_model=AskResponse)
def ask(req: str):
    t0 = time.time()
    out = run_agent(req)
    print(f"THIS TOOK {time.time() - t0} YEARS TO RUN !!!!!!!!!!!!!!!!!!!!!!!!")
    return AskResponse(**out)

@app.get("/health")
def health():
    return JSONResponse(content={ "status": "ok" }, status_code=200)
