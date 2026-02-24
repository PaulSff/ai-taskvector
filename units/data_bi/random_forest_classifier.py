"""RandomForestClassifier: fit/predict classification (sklearn)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _random_forest_classifier_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty) or not _HAS_PANDAS:
        return out_table([], state)
    target = params.get("target_column") or inputs.get("target_column")
    if not target or target not in df.columns:
        return out_table(df, state)
    try:
        from sklearn.ensemble import RandomForestClassifier
        from sklearn.metrics import accuracy_score
        X = df.drop(columns=[target]).select_dtypes(include=["number"])
        if X.empty:
            return out_table(df, state)
        y = df[target]
        model = state.get("model")
        if model is None:
            model = RandomForestClassifier(n_estimators=int(params.get("n_estimators", 100)), random_state=42)
            model.fit(X, y)
            state = {**state, "model": model}
        pred = model.predict(X)
        out_df = df.copy()
        out_df["_pred"] = pred
        acc = float(accuracy_score(y, pred))
        return out_table(out_df, state, {"accuracy": acc, "predictions": pred.tolist()})
    except Exception:
        return out_table(df, state)


def register_random_forest_classifier() -> None:
    register_unit(UnitSpec(
        type_name="RandomForestClassifier",
        input_ports=[("table", "table"), ("target_column", "str")],
        output_ports=[("row_count", "float"), ("table", "table"), ("accuracy", "float"), ("predictions", "list")],
        step_fn=_random_forest_classifier_step,
    ))
