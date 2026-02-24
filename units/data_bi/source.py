"""DataSource unit: load table from params (path/format) or pass-through from state. Uses pandas when available for read."""

from typing import Any

from units.data_bi._common import df_to_table, table_row_count, table_to_df
from units.registry import UnitSpec, register_unit


def _data_source_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """
    DataSource: outputs table from state (loaded at reset by spec) or params.
    If state has table, use it; else if params has path and pandas, read csv/json.
    """
    table = state.get("table")
    if table is None and params.get("data"):
        table = params["data"]
    if table is None and params.get("path"):
        try:
            import pandas as pd
            from pathlib import Path
            path = Path(params["path"])
            fmt = (params.get("format") or "json").lower()
            if path.exists():
                if fmt == "csv":
                    df = pd.read_csv(path)
                elif fmt in ("json", "jsonl"):
                    df = pd.read_json(path, lines=(fmt == "jsonl"))
                else:
                    df = pd.read_json(path)
                    if isinstance(df, dict):
                        for key in ("data", "offers", "rows"):
                            if key in df and isinstance(df[key], list):
                                df = pd.DataFrame(df[key])
                                break
                        else:
                            df = pd.DataFrame([df])
                table = df_to_table(df)
        except Exception:
            pass
    if table is None:
        table = []
    if not isinstance(table, list):
        table = []
    row_count = table_row_count(table)
    schema = list(table[0].keys()) if table else []
    return {
        "row_count": float(row_count),
        "table": table,
        "schema": schema,
    }, state


def register_data_source() -> None:
    register_unit(UnitSpec(
        type_name="DataSource",
        input_ports=[],  # no inputs; data from state/params
        output_ports=[("row_count", "float"), ("table", "table"), ("schema", "list")],
        step_fn=_data_source_step,
    ))
