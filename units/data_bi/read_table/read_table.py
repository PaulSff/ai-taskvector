"""ReadTable: load table from path (csv, json, jsonl, parquet, xlsx, xls)."""
from __future__ import annotations

from pathlib import Path
from typing import Any

from units.data_bi._common import _HAS_PANDAS, df_to_table, out_table, table_to_df
from units.registry import UnitSpec, register_unit


def _read_table_step(
    params: dict,
    inputs: dict,
    state: dict,
    dt: float,
) -> tuple[dict, dict]:
    path = params.get("path") or inputs.get("path") or state.get("path")
    fmt = (params.get("format") or params.get("file_format") or "").lower()
    table = state.get("table")
    if table is not None and not params.get("reload"):
        return out_table(table, state)
    if not path or not _HAS_PANDAS:
        return out_table([], state)

    import pandas as pd
    path = Path(path)
    if not path.exists():
        return out_table([], state)

    try:
        if fmt in ("csv", "csv.gz"):
            df = pd.read_csv(path)
        elif fmt in ("json", "jsonl", "ndjson"):
            if fmt in ("jsonl", "ndjson"):
                df = pd.read_json(path, lines=True)
            else:
                df = pd.read_json(path)
                if isinstance(df, dict):
                    for key in ("data", "offers", "rows", "records"):
                        if key in df and isinstance(df[key], list):
                            df = pd.DataFrame(df[key])
                            break
                    else:
                        df = pd.DataFrame([df] if isinstance(df, dict) else [])
        elif fmt == "parquet":
            df = pd.read_parquet(path)
        elif fmt in ("xlsx", "xls"):
            engine = "openpyxl" if path.suffix.lower() == ".xlsx" else "xlrd"
            read_formulas = params.get("read_formulas", False)
            if read_formulas and engine == "openpyxl":
                import openpyxl
                wb = openpyxl.load_workbook(path, data_only=False)
                sheet = wb.active
                rows = list(sheet.iter_rows(values_only=False))
                if not rows:
                    df = pd.DataFrame()
                else:
                    headers = [cell.value for cell in rows[0]]
                    data = [[cell.value for cell in r] for r in rows[1:]]
                    df = pd.DataFrame(data, columns=headers)
            else:
                df = pd.read_excel(path, engine=engine)
        else:
            df = pd.read_csv(path)
    except Exception:
        return out_table([], state)

    cols = list(df.columns)
    norm_cols = [
        None if (isinstance(c, str) and c.startswith("Unnamed:")) or c is None else c
        for c in cols
    ]
    df.columns = norm_cols

    def _col_letter(i: int) -> str:
        result = []
        n = i + 1
        while n:
            n, rem = divmod(n - 1, 26)
            result.append(chr(ord("A") + rem))
        return "".join(reversed(result))

    schema = [
        {"index": i, "letter": _col_letter(i), "name": col}
        for i, col in enumerate(norm_cols)
    ]

    tbl = df_to_table(df)
    state = {**state, "table": tbl, "path": str(path)}
    return {"row_count": float(len(tbl)), "table": tbl, "schema": schema}, state


def register_read_table() -> None:
    register_unit(UnitSpec(
        type_name="ReadTable",
        input_ports=[("path", "str")],
        output_ports=[("row_count", "float"), ("table", "table"), ("schema", "list")],
        step_fn=_read_table_step,
        controllable=True,
        description=(
            "Loads a table from path (csv, json, jsonl, parquet, xlsx, xls); "
            "outputs row_count, table, and schema. Can optionally read Excel formulas with read_formulas=True."
        ),
    ))