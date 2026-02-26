"""ReadTable: load table from path (csv, json, jsonl, parquet)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from units.data_bi._common import _HAS_PANDAS, df_to_table, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _read_table_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    path = params.get("path") or inputs.get("path") or state.get("path")
    fmt = (params.get("format") or params.get("file_format") or "json").lower()
    table = state.get("table")
    if table is not None and not params.get("reload"):
        return out_table(table, state)
    if not path or not _HAS_PANDAS:
        return out_table([], state)
    import pandas as pd
    path = Path(path)
    if not path.exists():
        return out_table([], state)
    try:
        if fmt in ("csv", "csv.gz"):
            df = pd.read_csv(path)
        elif fmt in ("json", "jsonl", "ndjson"):
            if fmt == "jsonl" or fmt == "ndjson":
                df = pd.read_json(path, lines=True)
            else:
                df = pd.read_json(path)
                if isinstance(df, dict):
                    for key in ("data", "offers", "rows", "records"):
                        if key in df and isinstance(df[key], list):
                            df = pd.DataFrame(df[key])
                            break
                    else:
                        df = pd.DataFrame([df] if isinstance(df, dict) else [])
        elif fmt == "parquet":
            df = pd.read_parquet(path)
        else:
            df = pd.read_csv(path)
    except Exception:
        return out_table([], state)
    tbl = df_to_table(df)
    state = {**state, "table": tbl, "path": str(path)}
    return {"row_count": float(len(tbl)), "table": tbl, "schema": list(df.columns) if len(df) else []}, state


def register_read_table() -> None:
    register_unit(UnitSpec(
        type_name="ReadTable",
        input_ports=[("path", "str")],
        output_ports=[("row_count", "float"), ("table", "table"), ("schema", "list")],
        step_fn=_read_table_step,
        controllable=True,
    ))
