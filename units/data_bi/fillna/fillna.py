"""FillNa: fill missing values (pandas fillna)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, df_to_table, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _fillna_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty):
        return out_table([], state)
    value = inputs.get("value") if "value" in inputs else params.get("value")
    if value is None:
        return out_table(df, state)
    if _HAS_PANDAS:
        df = df.fillna(value)
    else:
        tbl = df_to_table(df)
        tbl = [{k: (value if v is None or str(v) == "nan" else v) for k, v in row.items()} for row in tbl]
        return out_table(tbl, state)
    return out_table(df, state)


def register_fillna() -> None:
    register_unit(UnitSpec(
        type_name="FillNa",
        input_ports=[("table", "table"), ("value", "float")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_fillna_step,
        controllable=True,
    ))
