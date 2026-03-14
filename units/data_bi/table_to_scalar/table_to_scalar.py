"""TableToScalar: extract a scalar from a table (first row, sum, mean, etc.)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, table_to_df
from units.registry import UnitSpec, register_unit


def _table_to_scalar_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Get one scalar from the table: by column and aggregation (first, sum, mean, last, min, max)."""
    df = table_to_df(inputs.get("table"))
    column = params.get("column") or inputs.get("column")
    agg = (params.get("agg") or inputs.get("agg") or "first").strip().lower()
    default = params.get("default") if "default" in params else inputs.get("default")

    if df is None or (hasattr(df, "empty") and df.empty):
        return {"row_count": 0.0, "value": default}, state
    if not column:
        return {"row_count": float(len(df)), "value": default}, state

    if _HAS_PANDAS:
        import pandas as pd

        if column not in df.columns:
            return {"row_count": float(len(df)), "value": default}, state
        try:
            if agg == "first":
                val = df[column].iloc[0]
            elif agg == "last":
                val = df[column].iloc[-1]
            elif agg in ("sum", "mean", "min", "max"):
                val = getattr(df[column], agg)()
            elif agg == "count":
                val = float(df[column].count())
            else:
                val = df[column].iloc[0]
        except Exception:
            val = default
    else:
        tbl = df if isinstance(df, list) else []
        if not tbl or column not in (tbl[0] if isinstance(tbl[0], dict) else {}):
            return {"row_count": float(len(tbl)), "value": default}, state
        try:
            if agg == "first":
                val = tbl[0].get(column)
            elif agg == "last":
                val = tbl[-1].get(column)
            else:
                vals = [r.get(column) for r in tbl if isinstance(r, dict) and column in r]
                if agg == "sum":
                    val = sum(float(x) for x in vals if x is not None)
                elif agg == "mean":
                    vals = [float(x) for x in vals if x is not None]
                    val = sum(vals) / len(vals) if vals else default
                elif agg == "min":
                    val = min((float(x) for x in vals if x is not None), default=default)
                elif agg == "max":
                    val = max((float(x) for x in vals if x is not None), default=default)
                else:
                    val = tbl[0].get(column) if tbl else default
        except Exception:
            val = default

    return {"row_count": float(len(df)), "value": val}, state


def register_table_to_scalar() -> None:
    register_unit(UnitSpec(
        type_name="TableToScalar",
        input_ports=[("table", "table"), ("column", "str"), ("agg", "str"), ("default", "Any")],
        output_ports=[("row_count", "float"), ("value", "Any")],
        step_fn=_table_to_scalar_step,
        controllable=True,
        description="Extracts a scalar from the table: column + agg (first, last, sum, mean, min, max). Outputs row_count and value; uses default when table is empty or column missing.",
    ))

