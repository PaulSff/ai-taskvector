"""FilterRows: filter rows by query or column + op + value (pandas)."""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
import pandas as pd

from services.logging import setup_colored_logging
from units.data_bi._common import _HAS_PANDAS, df_to_table, out_table, table_to_df
from units.registry import UnitSpec, register_unit

logger = setup_colored_logging(logging.DEBUG)


def to_float_scalar(x: Any) -> float | None:
    if x is None:
        return None
    if isinstance(x, (pd.Series, pd.Index, np.ndarray)):
        if len(x) == 0:
            return None
        x = x[0]
    if pd.isna(x):
        return None
    return float(x)


def _filter_rows_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    df = table_to_df(inputs.get("table"))
    if df is None or (hasattr(df, "empty") and df.empty):
        return out_table([], state)
    if not _HAS_PANDAS:
        return out_table(df_to_table(df), state)

    query_expr = params.get("query") or inputs.get("query")
    column = params.get("column") or inputs.get("column")
    op = (params.get("op") or inputs.get("op") or "le").strip().lower()
    raw_val = inputs.get("value") if "value" in inputs else params.get("value")

    if query_expr:
        try:
            df = df.query(query_expr)
        except Exception:
            logger.exception("FilterRows: invalid query expression: %r", query_expr)
    elif column is not None and raw_val is not None:
        try:
            col = df[column].copy()

            # Convert to numpy array first to avoid extension array type issues
            try:
                # For datetime/timedelta, convert to int64 then float
                if pd.api.types.is_datetime64_any_dtype(col) or pd.api.types.is_timedelta64_dtype(col):
                    col_numeric = col.astype('int64').astype('float64') / 1e9
                else:
                    # Convert to numeric
                    col_numeric = pd.to_numeric(col, errors="coerce")

                    # If it's not a Series, the entire column is NA
                    if not isinstance(col_numeric, (pd.Series, pd.Index)):
                        raise ValueError("Column cannot be converted to numeric")

                    # Convert to native numpy float64 array
                    col_numeric = col_numeric.to_numpy(dtype='float64', na_value=np.nan)
            except (TypeError, ValueError, AttributeError):
                col_numeric = None

            # Check if conversion failed
            if col_numeric is None or np.isnan(col_numeric).all():
                raise ValueError("Column cannot be converted to numeric")

            try:
                numeric_val = pd.to_numeric(raw_val, errors="coerce")

                # Extract scalar if pd.to_numeric returned a Series/Index
                if isinstance(numeric_val, (pd.Series, pd.Index)):
                    arr = numeric_val.to_numpy()
                    numeric_val = arr[0] if len(arr) > 0 else None

                # Try to convert to float—let exceptions catch invalid/NA values
                try:
                    numeric_val = pd.to_numeric(raw_val, errors="coerce")
                    val = to_float_scalar(numeric_val)
                except (ValueError, TypeError, IndexError):
                    val = None
            except (ValueError, TypeError, IndexError):
                val = None


            if val is not None:
                # Now col_numeric is guaranteed to be float64—comparisons will work
                try:
                    if op == "lt":
                        comparison_mask = col_numeric < val
                    elif op == "le":
                        comparison_mask = col_numeric <= val
                    elif op == "gt":
                        comparison_mask = col_numeric > val
                    elif op == "ge":
                        comparison_mask = col_numeric >= val
                    elif op == "eq":
                        comparison_mask = col_numeric == val
                    elif op == "neq":
                        comparison_mask = col_numeric != val
                    else:
                        comparison_mask = col_numeric <= val

                    # Apply mask, treating NaN as False
                    comparison_mask = pd.Series(comparison_mask, index=df.index).fillna(False)
                    df = df[comparison_mask]
                except (ValueError, TypeError, IndexError):
                    pass
            else:
                # val is None—fall back to non-numeric comparison
                try:
                    if op == "eq":
                        df = df[df[column] == raw_val]
                    elif op == "neq":
                        df = df[df[column] != raw_val]
                except (ValueError, TypeError, IndexError):
                    pass

        except (ValueError, TypeError, KeyError):
            # Column doesn't exist or can't be converted—fall back to non-numeric
            try:
                if op == "eq":
                    df = df[df[column] == raw_val]
                elif op == "neq":
                    df = df[df[column] != raw_val]
            except (ValueError, TypeError, IndexError):
                pass

    return out_table(df, state)


def register_filter_rows() -> None:
    register_unit(UnitSpec(
        type_name="FilterRows",
        input_ports=[
            ("value", "float"),
            ("table", "table"),
            ("query", "str"),
            ("column", "str"),
            ("op", "str"),
        ],
        output_ports=[("row_count", "float"), ("table", "table")],
        step_fn=_filter_rows_step,
        controllable=True,
        description="Filters rows by column, operator, and value (query or column/op/value); agent can set value for RL.",
    ))
