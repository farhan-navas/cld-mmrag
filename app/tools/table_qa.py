import logging, re

import pandas as pd
from app.tools.models import TableQAInput, TableQAOutput

logger = logging.getLogger("tool.table_qa")

def _coerce_numeric_columns(df: pd.DataFrame) -> pd.DataFrame:
    for col in df.columns:
        s = df[col]
        if pd.api.types.is_numeric_dtype(s):
            continue

        # only try strings / objects
        if pd.api.types.is_string_dtype(s) or s.dtype == object:
            # normalize thousands separators, keep cheap + typed
            s2 = s.astype(str).str.replace(",", "", regex=False)
            num = pd.to_numeric(s2, errors="coerce")

            # keep numeric where possible, otherwise preserve original values
            df[col] = num.combine_first(s)
    return df

def _md_to_dataframe(md: str) -> pd.DataFrame:
    # Very simple GitHub-style markdown table parser
    lines = [ln.strip() for ln in md.splitlines() if ln.strip()]
    if len(lines) < 2:
        return pd.DataFrame()

    # Remove leading/trailing pipes, split on '|'
    def split_row(row: str):
        row = row.strip()
        if row.startswith("|"): row = row[1:]
        if row.endswith("|"): row = row[:-1]
        return [c.strip() for c in row.split("|")]

    header = split_row(lines[0])
    # Skip the separator line (lines[1])
    data_rows = [split_row(ln) for ln in lines[2:]]
    df = pd.DataFrame(data_rows, columns=header)
    df = _coerce_numeric_columns(df)
    return df

def table_qa(inp: TableQAInput) -> TableQAOutput:
    logger.info("table_qa start question=%r md_chars=%d", inp.question, len(inp.markdown or ""))

    df = _md_to_dataframe(inp.markdown)
    
    logger.debug("table parsed rows=%d cols=%d", len(df), len(df.columns))
    if df.empty:
        logger.info("table_qa empty_table")
        return TableQAOutput(short_answer="I couldn’t parse the table.", explanation="No rows/cols parsed.")

    q = inp.question.lower()

    # sum/avg/min/max of a column
    m = re.search(r"(sum|average|avg|max|min)\s+of\s+([A-Za-z0-9 _\-]+)", q)

    if m:
        op, col = m.group(1), m.group(2).strip()
        if col in df.columns:
            series = pd.to_numeric(df[col], errors="coerce")
            if op in ("average","avg"):
                val = float(series.mean(skipna=True))
            elif op == "sum":
                val = float(series.sum(skipna=True))
            elif op == "max":
                val = float(series.max(skipna=True))
            else:
                val = float(series.min(skipna=True))

            logger.info("table_qa aggregate op=%s col=%s rows=%d", op, col, len(df))
            return TableQAOutput(
                short_answer=f"{op} of {col}: {val:.4g}",
                explanation=f"Computed {op} over column '{col}' on {len(df)} rows."
            )

    # filter by equality: column=value
    m = re.search(r"(?:where|for)\s+([A-Za-z0-9 _\-]+)\s*=\s*([A-Za-z0-9 _\-/\.]+)", q)
    if m:
        col, val = m.group(1).strip(), m.group(2).strip()
        if col in df.columns:
            out = df[df[col].astype(str).str.lower() == val.lower()]
            head = out.head(5).to_dict(orient="records")
            
            logger.info("table_qa filter_eq col=%s val=%r matched_rows=%d", col, val, len(out))
            return TableQAOutput(
                short_answer=f"{len(out)} matching rows (showing up to 5).",
                explanation=f"Rows: {head}"
            )

    # fallback: describe table
    logger.info("table_qa fallback columns=%s rows=%d", list(df.columns), len(df))
    return TableQAOutput(
        short_answer="I can summarize or compute aggregates if you specify a column.",
        explanation=f"Columns: {list(df.columns)} | Rows: {len(df)}"
    )
