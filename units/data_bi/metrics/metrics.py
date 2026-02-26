"""Metrics: accuracy, F1, MSE, R² from y_true/y_pred columns (sklearn)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _metrics_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty) or not _HAS_PANDAS:
        return {"row_count": 0.0, "table": [], "accuracy": 0.0, "f1": 0.0, "mse": 0.0, "r2": 0.0}, state
    y_true_col = params.get("y_true") or inputs.get("y_true") or "y_true"
    y_pred_col = params.get("y_pred") or inputs.get("y_pred") or "_pred"
    if y_true_col not in df.columns or y_pred_col not in df.columns:
        return out_table(df, state, {"accuracy": 0.0, "f1": 0.0, "mse": 0.0, "r2": 0.0})
    try:
        from sklearn.metrics import accuracy_score, f1_score, mean_squared_error, r2_score
        y_true = df[y_true_col]
        y_pred = df[y_pred_col]
        if str(y_true.dtype) in ("object", "category", "int64", "bool") or len(y_true.unique()) < 20:
            acc = float(accuracy_score(y_true, y_pred))
            f1 = float(f1_score(y_true, y_pred, average="weighted", zero_division=0))
            return out_table(df, state, {"accuracy": acc, "f1": f1, "mse": 0.0, "r2": 0.0})
        mse = float(mean_squared_error(y_true, y_pred))
        r2 = float(r2_score(y_true, y_pred))
        return out_table(df, state, {"accuracy": 0.0, "f1": 0.0, "mse": mse, "r2": r2})
    except Exception:
        return out_table(df, state, {"accuracy": 0.0, "f1": 0.0, "mse": 0.0, "r2": 0.0})


def register_metrics() -> None:
    register_unit(UnitSpec(
        type_name="Metrics",
        input_ports=[("table", "table"), ("y_true", "str"), ("y_pred", "str")],
        output_ports=[("row_count", "float"), ("table", "table"), ("accuracy", "float"), ("f1", "float"), ("mse", "float"), ("r2", "float")],
        step_fn=_metrics_step,
        controllable=True,
    ))
