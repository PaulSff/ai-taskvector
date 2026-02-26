"""OneHotEncoder: one-hot encode categorical columns (sklearn)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _one_hot_encoder_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty) or not _HAS_PANDAS:
        return out_table([], state)
    try:
        from sklearn.preprocessing import OneHotEncoder
        cols = params.get("columns") or inputs.get("columns")
        if isinstance(cols, str):
            cols = [c.strip() for c in cols.split(",") if c.strip()]
        if not cols:
            cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
        if not cols:
            return out_table(df, state)
        enc = state.get("encoder")
        if enc is None:
            enc = OneHotEncoder(sparse_output=False, handle_unknown="ignore")
            enc.fit(df[cols])
            state = {**state, "encoder": enc}
        X = enc.transform(df[cols])
        cat_names = enc.get_feature_names_out()
        out_df = df.drop(columns=cols, errors="ignore")
        for i, name in enumerate(cat_names):
            out_df[name] = X[:, i]
        return out_table(out_df, state)
    except Exception:
        return out_table(df, state)


def register_one_hot_encoder() -> None:
    register_unit(UnitSpec(
        type_name="OneHotEncoder",
        input_ports=[("table", "table"), ("columns", "list")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_one_hot_encoder_step,
        controllable=True,
    ))
