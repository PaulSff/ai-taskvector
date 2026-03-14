"""DictToTable: convert a dictionary to a table (DataFrame / list of dicts)."""
from __future__ import annotations

from typing import Any

from units.data_bi._common import _HAS_PANDAS, df_to_table, out_table
from units.registry import UnitSpec, register_unit


def _dict_to_table_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    """Convert dict to one-row table (flat dict) or multi-row table (dict of lists)."""
    data = inputs.get("data") if "data" in inputs else inputs.get("in")
    if data is None or not _HAS_PANDAS:
        return out_table([], state)

    import pandas as pd

    if isinstance(data, dict):
        # Single record: {"Name": "Alice", "Age": 25} -> one row
        # Dict of lists: {"Name": ["A","B"], "Age": [25,30]} -> multiple rows
        try:
            if not data:
                return out_table([], state)
            first_val = next(iter(data.values()))
            if isinstance(first_val, (list, tuple)) and len(first_val) > 0:
                df = pd.DataFrame(data)
            else:
                df = pd.DataFrame([data])
        except Exception:
            df = pd.DataFrame([data])
    elif isinstance(data, list) and data and isinstance(data[0], dict):
        df = pd.DataFrame(data)
    else:
        return out_table([], state)

    return out_table(df, state)


def register_dict_to_table() -> None:
    register_unit(UnitSpec(
        type_name="DictToTable",
        input_ports=[("data", "Any")],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_dict_to_table_step,
        controllable=False,
        description="Converts a dictionary to a table (one row for flat dict, multiple rows for dict of lists). Uses pandas DataFrame.",
    ))
