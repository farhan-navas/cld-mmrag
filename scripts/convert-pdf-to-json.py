import json
import re
import pandas as pd

from camelot.io import read_pdf

PDF_PATH = "data/00 Chatbot on PDDM Info - Query List.pdf"
JSON_PATH = "data/validation/query-list.json"
COLS = ["sn", "query", "answer", "layer", "file"]

# 1. Read all tables from the PDF
tables = read_pdf(PDF_PATH, pages="all", flavor="lattice")
dfs = []

for t in tables:
    df = t.df.copy()

    # If page has a header row, drop it, use hardcoded col names 
    first_cell = str(df.iloc[0, 0]).strip().lower()
    if first_cell in ("sn", "s/n", "no"):
        df = df.iloc[1:]

    df = df.iloc[:, : len(COLS)]
    df.columns = COLS

    df = df.astype(str) # ensure str
    df = df.map(lambda x: re.sub(r"\s+", " ", x).strip())

    dfs.append(df)

full_df = pd.concat(dfs, ignore_index=True)
records = full_df.to_dict(orient="records")

with open(JSON_PATH, "w", encoding="utf-8") as f:
    json.dump(records, f, indent=2, ensure_ascii=False)
