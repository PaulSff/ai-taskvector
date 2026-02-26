"""DropNa: drop rows with missing values (pandas dropna)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, df_to_table, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _dropna_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty):
        return out_table([], state)
    if _HAS_PANDAS:
        subset = params.get("subset") or inputs.get("subset")
        if isinstance(subset, str):
            subset = [s.strip() for s in subset.split(",") if s.strip()]
        df = df.dropna(subset=subset if subset else None)
    else:
        tbl = df_to_table(df)
        tbl = [row for row in tbl if all(v is not None and (str(v) != "nan") for v in row.values())]
        return out_table(tbl, state)
    return out_table(df, state)


def register_dropna() -> None:
    register_unit(UnitSpec(
        type_name="DropNa",
        input_ports=[("table", "table"), ("subset", "list")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_dropna_step,
        controllable=True,
    ))
