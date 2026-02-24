"""TrainTestSplit: split table into train/test (sklearn)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import df_to_table, table_to_df
from units.registry import UnitSpec, register_unit


def _train_test_split_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty):
        return {"row_count": 0.0, "table": [], "train": [], "test": []}, state
    try:
        from sklearn.model_selection import train_test_split
        test_size = float(params.get("test_size", inputs.get("test_size", 0.2)))
        seed = int(params.get("random_state", inputs.get("random_state", 42)))
        train_df, test_df = train_test_split(df, test_size=test_size, random_state=seed)
        train_tbl = df_to_table(train_df)
        test_tbl = df_to_table(test_df)
        state = {**state, "train": train_tbl, "test": test_tbl}
        return {
            "row_count": float(len(train_tbl) + len(test_tbl)),
            "table": train_tbl,
            "train": train_tbl,
            "test": test_tbl,
        }, state
    except Exception:
        return {"row_count": float(len(df)), "table": df_to_table(df), "train": [], "test": []}, state


def register_train_test_split() -> None:
    register_unit(UnitSpec(
        type_name="TrainTestSplit",
        input_ports=[("table", "table"), ("test_size", "float")],
        output_ports=[("row_count", "float"), ("table", "table"), ("train", "table"), ("test", "table")],
        step_fn=_train_test_split_step,
    ))
