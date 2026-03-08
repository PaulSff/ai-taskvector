"""PCA: dimensionality reduction (sklearn)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _pca_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty) or not _HAS_PANDAS:
        return out_table([], state)
    try:
        from sklearn.decomposition import PCA
        n_components = int(params.get("n_components", inputs.get("n_components", 2)))
        num_cols = df.select_dtypes(include=["number"]).columns.tolist()
        if not num_cols:
            return out_table(df, state)
        pca = state.get("pca")
        if pca is None:
            pca = PCA(n_components=min(n_components, len(num_cols), len(df)))
            pca.fit(df[num_cols])
            state = {**state, "pca": pca}
        X = pca.transform(df[num_cols])
        out_df = df.drop(columns=num_cols, errors="ignore")
        for i in range(X.shape[1]):
            out_df[f"PC{i+1}"] = X[:, i]
        return out_table(out_df, state)
    except Exception:
        return out_table(df, state)


def register_pca() -> None:
    register_unit(UnitSpec(
        type_name="PCA",
        input_ports=[("table", "table"), ("n_components", "int")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_pca_step,
        controllable=True,
        description="Principal component analysis: reduces numeric columns to n_components dimensions.",
    ))
