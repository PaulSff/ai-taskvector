"""RandomForestRegressor: fit/predict regression (sklearn)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _random_forest_regressor_step(
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
        from sklearn.ensemble import RandomForestRegressor
        from sklearn.metrics import mean_squared_error, r2_score
        X = df.drop(columns=[target]).select_dtypes(include=["number"])
        if X.empty:
            return out_table(df, state)
        y = df[target]
        model = state.get("model")
        if model is None:
            model = RandomForestRegressor(n_estimators=int(params.get("n_estimators", 100)), random_state=42)
            model.fit(X, y)
            state = {**state, "model": model}
        pred = model.predict(X)
        out_df = df.copy()
        out_df["_pred"] = pred
        mse = float(mean_squared_error(y, pred))
        r2 = float(r2_score(y, pred))
        return out_table(out_df, state, {"mse": mse, "r2": r2, "predictions": pred.tolist()})
    except Exception:
        return out_table(df, state)


def register_random_forest_regressor() -> None:
    register_unit(UnitSpec(
        type_name="RandomForestRegressor",
        input_ports=[("table", "table"), ("target_column", "str")],
        output_ports=[("row_count", "float"), ("table", "table"), ("mse", "float"), ("r2", "float"), ("predictions", "list")],
        step_fn=_random_forest_regressor_step,
        controllable=True,
        description="Fits a random forest regressor and outputs predictions plus MSE/R².",
    ))
