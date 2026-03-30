"""TablesToText: convert a list of tables to one string (CSV per table, joined). Uses pandas.
Accepts tables in legacy form (list-of-row-dicts) or new form [{"rows": [...], "schema": [...]}].
Cells that are dicts {"value": ..., "formula": ...} are exported using the "value".
"""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, table_to_df
from units.registry import UnitSpec, register_unit


def _table_rows_from_input(t):
    """Normalize input table to a list-of-row-dicts suitable for DataFrame construction.
    Accepts either:
      - list of row dicts (legacy)
      - dict with keys "rows" and optional "schema"
    """
    if isinstance(t, dict) and "rows" in t:
        return t.get("rows") or []
    if isinstance(t, list):
        return t
    return []


def _normalize_table_for_df(t):
    if not _HAS_PANDAS:
        return None
    import pandas as pd

    rows = _table_rows_from_input(t)
    # If rows is empty but t might be another table format, fall back to table_to_df
    if not rows:
        try:
            df = table_to_df(t)
            return df
        except Exception:
            return pd.DataFrame()

    out_rows = []
    for r in rows:
        if not isinstance(r, dict):
            out_rows.append(r)
            continue
        new_r = {}
        for k, v in r.items():
            if isinstance(v, dict) and "value" in v:
                new_r[k] = v.get("value")
            else:
                new_r[k] = v
        out_rows.append(new_r)
    return pd.DataFrame(out_rows) if out_rows else pd.DataFrame()


def _tables_to_text_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    tables = inputs.get("tables")
    if not _HAS_PANDAS:
        return ({"text": "", "row_count": 0.0}, state)
    if tables is None:
        return ({"text": "", "row_count": 0.0}, state)
    if not isinstance(tables, list):
        return ({"text": "", "row_count": 0.0}, state)

    fmt = (params.get("format") or "csv").strip().lower()
    parts: list[str] = []
    total_rows = 0
    for t in tables:
        if t is None:
            continue
        df = _normalize_table_for_df(t)
        if df is None or (hasattr(df, "empty") and df.empty):
            continue
        total_rows += len(df)
        if fmt == "csv":
            parts.append(df.to_csv(index=False, lineterminator="\n"))
        else:
            parts.append(df.to_string(index=False))
    text = "\n\n".join(p.strip() for p in parts if (p or "").strip())
    return ({"text": text, "row_count": float(total_rows)}, state)


def register_tables_to_text() -> None:
    register_unit(UnitSpec(
        type_name="TablesToText",
        input_ports=[("tables", "Any")],
        output_ports=[("text", "str"), ("row_count", "float")],
        step_fn=_tables_to_text_step,
        controllable=False,
        description="Converts a list of tables to one string. Each table is exported as CSV (or plain text). Uses pandas. For RAG or document indexing.",
    ))


__all__ = ["register_tables_to_text"]
