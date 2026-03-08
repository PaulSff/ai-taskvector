"""LogisticRegression: fit/predict classification (sklearn)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _logistic_regression_step(
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
        from sklearn.linear_model import LogisticRegression
        from sklearn.metrics import accuracy_score
        X = df.drop(columns=[target]).select_dtypes(include=["number"])
        if X.empty:
            return out_table(df, state)
        y = df[target]
        model = state.get("model")
        if model is None:
            model = LogisticRegression(max_iter=1000, random_state=42)
            model.fit(X, y)
            state = {**state, "model": model}
        pred = model.predict(X)
        proba = model.predict_proba(X)[:, 1] if hasattr(model, "predict_proba") and len(model.classes_) == 2 else pred
        out_df = df.copy()
        out_df["_pred"] = pred
        out_df["_proba"] = proba
        acc = float(accuracy_score(y, pred))
        return out_table(out_df, state, {"accuracy": acc, "predictions": pred.tolist()})
    except Exception:
        return out_table(df, state)


def register_logistic_regression() -> None:
    register_unit(UnitSpec(
        type_name="LogisticRegression",
        input_ports=[("table", "table"), ("target_column", "str")],
        output_ports=[("row_count", "float"), ("table", "table"), ("accuracy", "float"), ("predictions", "list")],
        step_fn=_logistic_regression_step,
        controllable=True,
        description="Fits a logistic regression classifier and outputs predictions plus accuracy.",
    ))
