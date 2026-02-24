"""StandardScaler: fit/transform numeric columns (sklearn)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _standard_scaler_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty):
        return out_table([], state)
    try:
        from sklearn.preprocessing import StandardScaler
        num_cols = df.select_dtypes(include=["number"]).columns.tolist()
        if not num_cols:
            return out_table(df, state)
        scaler = state.get("scaler")
        if scaler is None:
            scaler = StandardScaler()
            scaler.fit(df[num_cols])
            state = {**state, "scaler": scaler}
        X = scaler.transform(df[num_cols])
        out_df = df.copy()
        out_df[num_cols] = X
        return out_table(out_df, state)
    except Exception:
        return out_table(df, state)


def register_standard_scaler() -> None:
    register_unit(UnitSpec(
        type_name="StandardScaler",
        input_ports=[("table", "table")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_standard_scaler_step,
    ))
