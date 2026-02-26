"""Describe: numeric summary stats (pandas describe)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _describe_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty) or not _HAS_PANDAS:
        return out_table([], state)
    desc = df.describe()
    if desc is not None:
        desc = desc.reset_index()
    return out_table(desc, state)


def register_describe() -> None:
    register_unit(UnitSpec(
        type_name="Describe",
        input_ports=[("table", "table")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_describe_step,
        controllable=True,
    ))
