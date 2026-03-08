"""TopK unit: take first K rows (pandas head when available)."""

from typing import Any

from units.data_bi._common import df_to_table, table_to_df
from units.registry import UnitSpec, register_unit


def _topk_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """TopK: table + k -> first k rows. Uses pandas head() when available."""
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty):
        return {"row_count": 0.0, "table": []}, state
    k = inputs.get("k") or params.get("k") or 10
    try:
        k = int(k)
    except (TypeError, ValueError):
        k = 10
    n = len(df) if hasattr(df, "__len__") else 0
    k = max(1, min(k, n))
    if hasattr(df, "head"):
        df = df.head(k)
        tbl = df_to_table(df)
    else:
        tbl = (df[:k] if isinstance(df, list) else df_to_table(df)[:k])
    return {"row_count": float(len(tbl)), "table": tbl}, state


def register_topk() -> None:
    register_unit(UnitSpec(
        type_name="TopK",
        input_ports=[("table", "table"), ("k", "int")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_topk_step,
        controllable=True,
        description="Keeps only the top K rows by a sort column; k can be wired as action for RL.",
    ))
