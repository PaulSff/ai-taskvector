"""KMeans: clustering (sklearn)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _kmeans_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty) or not _HAS_PANDAS:
        return out_table([], state)
    try:
        from sklearn.cluster import KMeans
        n_clusters = int(params.get("n_clusters", inputs.get("n_clusters", 3)))
        X = df.select_dtypes(include=["number"])
        if X.empty:
            return out_table(df, state)
        model = state.get("model")
        if model is None:
            model = KMeans(n_clusters=min(n_clusters, len(df)), random_state=42)
            model.fit(X)
            state = {**state, "model": model}
        pred = model.predict(X)
        out_df = df.copy()
        out_df["_cluster"] = pred
        return out_table(out_df, state, {"predictions": pred.tolist()})
    except Exception:
        return out_table(df, state)


def register_kmeans() -> None:
    register_unit(UnitSpec(
        type_name="KMeans",
        input_ports=[("table", "table"), ("n_clusters", "int")],
        output_ports=[("row_count", "float"), ("table", "table"), ("predictions", "list")],
        step_fn=_kmeans_step,
        controllable=True,
    ))
