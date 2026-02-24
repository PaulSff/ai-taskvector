"""MergeTables: join two tables (pandas merge)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _merge_tables_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    left = table_to_df(inputs.get("left") or inputs.get("table"))
    right = table_to_df(inputs.get("right"))
    if left is None or (hasattr(left, "empty") and left.empty):
        return out_table([], state)
    if right is None or (hasattr(right, "empty") and right.empty):
        return out_table(left, state)
    if not _HAS_PANDAS:
        return out_table(left, state)
    import pandas as pd
    on = params.get("on") or inputs.get("on")
    how = (params.get("how") or inputs.get("how") or "inner").lower()
    try:
        df = pd.merge(left, right, on=on if isinstance(on, list) else [on] if on else None, how=how)
    except Exception:
        df = left
    return out_table(df, state)


def register_merge_tables() -> None:
    register_unit(UnitSpec(
        type_name="MergeTables",
        input_ports=[("left", "table"), ("right", "table"), ("on", "str"), ("how", "str")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_merge_tables_step,
    ))
