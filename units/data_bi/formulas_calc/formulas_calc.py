"""
units/canonical/formulas/formulas_calc.py

Data_bi unit implementing the "formulas_calc" action using the `formulas`
package (https://pypi.org/project/formulas/). It preserves the action-command
API: action dict with keys {"action":"formulas_calc","path":...,"inputs":{...},
"outputs":[...],"output-format":"json"}.

Ports:
 - input:  ("action", "Any")
 - outputs: ("results", "Any"), ("error", "str")

Assumptions / targeted formulas API (common patterns across formulas versions):
 - **Legacy:** ``formulas.ExcelCompiler().read(path)`` -> workbook, compile/recalculate, read cells.
 - **Modern (1.3.x):** ``ExcelCompiler`` removed; use ``ExcelModel().load(path).finish()`` then
   ``calculate()``; optional ``from_dict`` overrides; read results from the returned solution (Ranges).

Adjust minor call names if your installed formulas version differs; comments indicate where to change.
"""

from pathlib import Path
from typing import Any, Dict, List, Tuple

import re

from units.registry import UnitSpec, register_unit


INPUT_PORTS = [("action", "Any"), ("parser_output", "Any")]
OUTPUT_PORTS = [("results", "Any"), ("error", "str")]


# --- Helpers: parse references & ranges -------------------------------------

_cell_ref_re = re.compile(r"(?:(?:'?\[.*?\])?('?(.+?)'?)!)?(?P<addr>.+)", re.IGNORECASE)
# matches optional "'[file]SHEET'!" or "SHEET!" then the address (A1 or A1:A3 etc)

def _a1_col_label(col_1based: int) -> str:
    """1-based column index to Excel letters (1 -> A, 27 -> AA)."""
    n = int(col_1based)
    if n < 1:
        raise ValueError(f"invalid column index: {col_1based}")
    letters: List[str] = []
    while n > 0:
        n, rem = divmod(n - 1, 26)
        letters.append(chr(ord("A") + rem))
    return "".join(reversed(letters))


def _split_sheet_and_addr(raw: str) -> Tuple[str | None, str]:
    """
    Parse forms like:
      "'[excel.xlsx]DATA'!B3"
      "DATA!B3"
      "B3"
    Returns (sheet_name or None, addr_str)
    """
    s = raw.strip()
    m = _cell_ref_re.match(s)
    if not m:
        return None, s
    full = m.group(0)
    # crude split: find rightmost '!' if present
    if "!" in s:
        parts = s.rsplit("!", 1)
        sheet_part = parts[0].strip().strip("'").strip()
        addr = parts[1].strip()
        # remove possible file prefix [file] from sheet_part
        if "]" in sheet_part:
            # e.g. [excel.xlsx]DATA  or '[excel.xlsx]DATA'
            try:
                sheet_name = sheet_part.split("]", 1)[1]
            except Exception:
                sheet_name = sheet_part
        else:
            sheet_name = sheet_part
        return sheet_name, addr
    else:
        return None, s


def _col_row_from_a1(addr: str) -> Tuple[int, int]:
    """
    Convert A1 -> (col_index, row_index) where both are 1-based.
    Simple handling: letters then digits.
    """
    addr = addr.upper()
    m = re.match(r"^([A-Z]+)(\d+)$", addr)
    if not m:
        raise ValueError(f"invalid A1 address: {addr}")
    col_letters, row_str = m.group(1), m.group(2)
    col = 0
    for ch in col_letters:
        col = col * 26 + (ord(ch) - ord("A") + 1)
    row = int(row_str)
    return col, row


def _expand_range(addr: str) -> List[Tuple[int, int]]:
    """
    Expand A1 or A1:B3 into list of (col,row) tuples (1-based).
    For single cell returns a single-item list.
    """
    if ":" not in addr:
        c, r = _col_row_from_a1(addr)
        return [(c, r)]
    start, end = addr.split(":", 1)
    c1, r1 = _col_row_from_a1(start.strip())
    c2, r2 = _col_row_from_a1(end.strip())
    cols = range(min(c1, c2), max(c1, c2) + 1)
    rows = range(min(r1, r2), max(r1, r2) + 1)
    coords = []
    for rr in rows:
        for cc in cols:
            coords.append((cc, rr))
    return coords


# --- formulas 1.3+ (ExcelModel) ---------------------------------------------


def _ranges_value_to_python(val: Any) -> Any:
    """Turn formulas ``Ranges`` (or similar) into JSON-friendly scalars / nested lists."""
    if val is None:
        return None
    cls_name = type(val).__name__
    if cls_name == "XlError" or "Error" in cls_name and hasattr(val, "value"):
        return str(val)
    if hasattr(val, "value"):
        arr = val.value
        try:
            import numpy as np

            if hasattr(arr, "shape"):
                if arr.size == 1:
                    x = arr.flat[0]
                    return x.item() if isinstance(x, np.generic) else x
                return arr.tolist()
        except Exception:
            pass
        return arr
    return val


def _excel_model_cell_token(sol_key: str) -> str:
    ks = str(sol_key)
    if "!" not in ks:
        return ks.strip().strip("'").upper()
    return ks.rsplit("!", 1)[-1].strip().strip("'").upper()


def _excel_model_sheet_blob_lower(sol_key: str) -> str:
    ks = str(sol_key)
    if "!" not in ks:
        return ""
    left = ks.rsplit("!", 1)[0]
    return left.lower()


def _excel_model_find_sol_key(
    sol: dict[Any, Any],
    user_sheet_hint: str | None,
    addr_token: str,
) -> str | None:
    at = addr_token.strip().upper()
    candidates = [k for k in sol if _excel_model_cell_token(str(k)) == at]
    if not candidates:
        return None
    if user_sheet_hint:
        h = user_sheet_hint.strip().lower()
        for k in candidates:
            if h in _excel_model_sheet_blob_lower(str(k)):
                return str(k)
    return str(candidates[0])


def _excel_model_resolve_input_key(sol_probe: dict[Any, Any], raw_key: str) -> str | None:
    sh, addr = _split_sheet_and_addr(str(raw_key))
    if ":" in addr:
        addr = addr.split(":", 1)[0].strip()
    try:
        _expand_range(addr)
    except Exception:
        return None
    return _excel_model_find_sol_key(sol_probe, sh, addr.upper())


def _formulas_excel_model_roundtrip(
    formulas_mod: Any,
    path: str,
    provided_inputs: Dict[str, Any],
    requested_outputs: List[Any],
    out_fmt: str,
    state: Dict[str, Any],
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """Evaluate workbook using ``formulas.ExcelModel`` (1.3.x)."""
    results: Dict[str, Any] = {}
    p = Path(str(path).strip())
    if not p.is_file():
        return {"results": {}, "error": f"workbook not found: {path}"}, state
    abs_path = str(p.resolve())

    model = formulas_mod.ExcelModel()
    model.load(abs_path)
    model.finish()
    sol_probe = model.calculate()

    overrides: Dict[str, Any] = {}
    for raw_k, val in provided_inputs.items():
        sk = _excel_model_resolve_input_key(sol_probe, str(raw_k))
        if sk is not None:
            overrides[sk] = val

    model2 = formulas_mod.ExcelModel()
    model2.load(abs_path)
    model2.finish()
    if overrides:
        model2.from_dict(overrides)
    sol = model2.calculate()

    if not requested_outputs:
        fmt = (out_fmt or "json").lower()
        out = results if fmt in ("json", "raw") else results
        return {"results": out, "error": ""}, state

    try:
        for raw_out in requested_outputs:
            sheet_name, addr = _split_sheet_and_addr(str(raw_out))
            if ":" in addr:
                coords = _expand_range(addr)
                cols = [c for c, _ in coords]
                rows = [r for _, r in coords]
                min_c, max_c = min(cols), max(cols)
                min_r, max_r = min(rows), max(rows)
                out_grid: List[List[Any]] = []
                for rr in range(min_r, max_r + 1):
                    row_vals: List[Any] = []
                    for cc in range(min_c, max_c + 1):
                        a1 = f"{_a1_col_label(cc)}{rr}"
                        ck = _excel_model_find_sol_key(sol, sheet_name, a1.upper())
                        row_vals.append(
                            _ranges_value_to_python(sol[ck]) if ck is not None and ck in sol else None
                        )
                    out_grid.append(row_vals)
                results[str(raw_out)] = out_grid
            else:
                ck = _excel_model_find_sol_key(sol, sheet_name, addr.strip().upper())
                results[str(raw_out)] = (
                    _ranges_value_to_python(sol[ck]) if ck is not None and ck in sol else None
                )
    except Exception as e:
        return {"results": {}, "error": f"collect_outputs failed: {e}"}, state

    fmt = (out_fmt or "json").lower()
    formatted = results if fmt in ("json", "raw") else results
    return {"results": formatted, "error": ""}, state


# --- Core step function -----------------------------------------------------


def _formulas_step(
    params: Dict[str, Any],
    inputs: Dict[str, Any],
    state: Dict[str, Any],
    dt: float,
) -> Tuple[Dict[str, Any], Dict[str, Any]]:
    """
    params: Unit params (may contain an action dict fallback)
    inputs: may contain 'action' dict injected by executor
    state: kept unchanged (stateless)
    """

    # default outputs
    results: Dict[str, Any] = {}
    error_msg = ""

    # 1) Get action dict (prefer parser_output from ProcessAgent, then inject action)
    action_cmd = None
    parser_out = inputs.get("parser_output") if inputs else None
    if isinstance(parser_out, dict):
        fcw = parser_out.get("formulas_calc")
        if isinstance(fcw, dict) and fcw.get("action") == "formulas_calc":
            action_cmd = fcw
    if action_cmd is None:
        if isinstance(inputs.get("action"), dict):
            action_cmd = inputs["action"]
        elif isinstance(params.get("action"), dict):
            action_cmd = params["action"]
        elif params.get("action") == "formulas_calc" or params.get("type") == "formulas_calc":
            action_cmd = {
                "action": params.get("action"),
                "path": params.get("path"),
                "inputs": params.get("inputs", {}),
                "outputs": params.get("outputs", []),
                "output-format": params.get("output-format", "json"),
            }

    if not action_cmd:
        # nothing to do
        return {"results": {}, "error": ""}, state

    if action_cmd.get("action") != "formulas_calc":
        return {"results": {}, "error": f"unsupported action: {action_cmd.get('action')}"}, state

    path = action_cmd.get("path")
    provided_inputs = action_cmd.get("inputs", {}) or {}
    requested_outputs = action_cmd.get("outputs", []) or []
    out_fmt = action_cmd.get("output-format", action_cmd.get("output_format", "json"))

    # 2) Import formulas
    try:
        import formulas
    except Exception as e:
        return {"results": {}, "error": f"import formulas failed: {e}"}, state

    # 2b) formulas 1.3+: ExcelModel only (no ExcelCompiler)
    if not hasattr(formulas, "ExcelCompiler") and hasattr(formulas, "ExcelModel"):
        if not path or not str(path).strip():
            return {"results": {}, "error": "formulas_calc requires path for ExcelModel"}, state
        try:
            return _formulas_excel_model_roundtrip(
                formulas,
                str(path),
                provided_inputs,
                requested_outputs,
                str(out_fmt),
                state,
            )
        except Exception as e:
            return {"results": {}, "error": f"ExcelModel evaluation failed: {e}"}, state

    # 3) Read workbook using ExcelCompiler if available
    workbook = None
    compiler = None
    try:
        # prefer ExcelCompiler when available
        if hasattr(formulas, "ExcelCompiler"):
            compiler = formulas.ExcelCompiler()
            if path:
                workbook = compiler.read(path)
            else:
                # some versions allow compiler.read_xml or creating empty workbook; fallback to None
                workbook = getattr(compiler, "create_workbook", lambda: None)()
        else:
            # fallback to Parser usage
            parser = getattr(formulas, "Parser", None)
            if parser is None:
                raise RuntimeError("formulas has no ExcelCompiler or Parser API in this environment")
            compiler = parser()
            if path:
                # some Parser variants offer read or loads; try read first
                read = getattr(compiler, "read", None)
                if callable(read):
                    workbook = read(path)
                else:
                    # try load from file content
                    with open(path, "rb") as f:
                        content = f.read()
                    workbook = compiler.loads(content)
            else:
                workbook = getattr(compiler, "create_workbook", lambda: None)()
    except Exception as e:
        return {"results": {}, "error": f"workbook load failed: {e}"}, state

    if workbook is None:
        return {"results": {}, "error": "failed to obtain workbook from formulas library"}, state

    # Helper to find sheet object
    def _get_sheet(sheet_name: str):
        if not sheet_name:
            # choose first sheet
            try:
                # workbook.sheets often is an ordered dict
                sheets_map = getattr(workbook, "sheets", None)
                if sheets_map:
                    # return first sheet object
                    for k in sheets_map:
                        return sheets_map[k]
                # fallback: workbook.worksheets or workbook.sheets[0]
                if hasattr(workbook, "worksheets"):
                    ws = getattr(workbook, "worksheets")
                    if ws:
                        return ws[0]
            except Exception:
                pass
            raise KeyError("no sheet specified and workbook has no accessible default sheet")
        # normal path: lookup by name (case-insensitive)
        sheets_map = getattr(workbook, "sheets", None) or getattr(workbook, "worksheets", None)
        if not sheets_map:
            raise KeyError("workbook has no sheets mapping")
        # if sheets_map is a dict-like
        try:
            # direct
            if sheet_name in sheets_map:
                return sheets_map[sheet_name]
            # case-insensitive search
            for key in sheets_map:
                if str(key).strip().lower() == sheet_name.strip().lower():
                    return sheets_map[key]
        except Exception:
            pass
        # try attribute access
        try:
            return getattr(workbook, sheet_name)
        except Exception:
            raise KeyError(f"sheet not found: {sheet_name}")

    # 4) Apply overrides from provided_inputs
    try:
        for raw_key, val in provided_inputs.items():
            sheet_name, addr = _split_sheet_and_addr(str(raw_key))
            sheet = _get_sheet(sheet_name) if sheet_name else _get_sheet(None)
            # handle ranges or single cells; try methods used by formulas internals
            if ":" in addr:
                coords = _expand_range(addr)
                # set the first cell or set all cells if provided value is list-like
                # If val is scalar -> set the first cell only
                if hasattr(val, "__iter__") and not isinstance(val, (str, bytes, dict)):
                    # flatten: assume list-of-lists or single list
                    flat = list(val)
                else:
                    flat = None
                # iterate coordinates and assign values if possible
                for idx, (c, r) in enumerate(coords):
                    # many formulas libs provide sheet.cell(c,r) or sheet.cell_at((r-1,c-1))
                    cell_obj = None
                    if hasattr(sheet, "cell"):
                        try:
                            cell_obj = sheet.cell(f"{_a1_col_label(c)}{r}") if callable(sheet.cell) else None
                        except Exception:
                            cell_obj = None
                    # try cell_by_rowcol style
                    if cell_obj is None:
                        # try by tuple indexing or mapping
                        try:
                            cell_obj = sheet.cells[(r, c)]
                        except Exception:
                            try:
                                cell_obj = sheet.cell_at((r, c))
                            except Exception:
                                cell_obj = None
                    if cell_obj is None:
                        # best-effort: skip if can't find a cell object
                        continue
                    # choose source value for this cell
                    if flat is None:
                        set_val = val
                    else:
                        # cycle or pick corresponding element
                        set_val = flat[idx] if idx < len(flat) else flat[-1]
                    # write to cell raw_value or value attribute depending on API
                    if hasattr(cell_obj, "raw_value"):
                        cell_obj.raw_value = set_val
                    elif hasattr(cell_obj, "value"):
                        try:
                            cell_obj.value = set_val
                        except Exception:
                            # some cell.value are read-only; try setting .raw
                            if hasattr(cell_obj, "raw"):
                                cell_obj.raw = set_val
                    else:
                        # fallback: try dict-like assignment
                        try:
                            sheet[(r, c)].value = set_val
                        except Exception:
                            pass
            else:
                # single cell
                coords = _expand_range(addr)
                c, r = coords[0]
                cell_obj = None
                # several possible access patterns
                try:
                    # common formulas versions: sheet.cell('A1') returns cell
                    cell_obj = sheet.cell(addr)
                except Exception:
                    try:
                        cell_obj = sheet.cells[(r, c)]
                    except Exception:
                        try:
                            cell_obj = sheet.cell_at((r, c))
                        except Exception:
                            cell_obj = None
                if cell_obj is None:
                    # best-effort: continue
                    continue
                if hasattr(cell_obj, "raw_value"):
                    cell_obj.raw_value = val
                elif hasattr(cell_obj, "value"):
                    try:
                        cell_obj.value = val
                    except Exception:
                        if hasattr(cell_obj, "raw"):
                            cell_obj.raw = val
                        else:
                            # last resort: setattr
                            try:
                                setattr(cell_obj, "value", val)
                            except Exception:
                                pass
    except Exception as e:
        return {"results": {}, "error": f"apply_overrides failed: {e}"}, state

    # 5) Compile / evaluate
    try:
        # many formulas distributions expect compiler.compile(workbook) then workbook.recalculate()
        if compiler is not None and hasattr(compiler, "compile"):
            try:
                compiler.compile(workbook)
            except Exception:
                # some versions use compiler.compile(workbook) that may raise; ignore and try evaluate
                pass

        if hasattr(workbook, "recalculate"):
            workbook.recalculate()
        elif hasattr(workbook, "evaluate"):
            workbook.evaluate()
        elif hasattr(compiler, "evaluate_all"):
            compiler.evaluate_all(workbook)
        else:
            # best-effort: try evaluator pattern
            evaluator = getattr(workbook, "evaluator", None)
            if callable(evaluator):
                evaluator()
    except Exception as e:
        return {"results": {}, "error": f"recalculation/evaluation failed: {e}"}, state

    # 6) Collect requested outputs
    try:
        for raw_out in requested_outputs:
            sheet_name, addr = _split_sheet_and_addr(str(raw_out))
            sheet = _get_sheet(sheet_name) if sheet_name else _get_sheet(None)
            if ":" in addr:
                coords = _expand_range(addr)
                # build rows/cols shape
                # determine min/max to shape nested lists
                cols = [c for c, _ in coords]
                rows = [r for _, r in coords]
                min_c, max_c = min(cols), max(cols)
                min_r, max_r = min(rows), max(rows)
                out_grid: List[List[Any]] = []
                for rr in range(min_r, max_r + 1):
                    row_vals: List[Any] = []
                    for cc in range(min_c, max_c + 1):
                        # locate cell object
                        cell_obj = None
                        try:
                            cell_obj = sheet.cell(f"{_a1_col_label(cc)}{rr}")
                        except Exception:
                            try:
                                cell_obj = sheet.cells[(rr, cc)]
                            except Exception:
                                try:
                                    cell_obj = sheet.cell_at((rr, cc))
                                except Exception:
                                    cell_obj = None
                        if cell_obj is None:
                            row_vals.append(None)
                        else:
                            # prefer .value, then .result, then .raw_value
                            val = None
                            for attr in ("value", "result", "raw_value", "raw"):
                                if hasattr(cell_obj, attr):
                                    val = getattr(cell_obj, attr)
                                    break
                            row_vals.append(val)
                    out_grid.append(row_vals)
                results[str(raw_out)] = out_grid
            else:
                # single cell
                coords = _expand_range(addr)
                c, r = coords[0]
                cell_obj = None
                try:
                    cell_obj = sheet.cell(addr)
                except Exception:
                    try:
                        cell_obj = sheet.cells[(r, c)]
                    except Exception:
                        try:
                            cell_obj = sheet.cell_at((r, c))
                        except Exception:
                            cell_obj = None
                if cell_obj is None:
                    results[str(raw_out)] = None
                else:
                    val = None
                    for attr in ("value", "result", "raw_value", "raw"):
                        if hasattr(cell_obj, attr):
                            val = getattr(cell_obj, attr)
                            break
                    results[str(raw_out)] = val
    except Exception as e:
        return {"results": {}, "error": f"collect_outputs failed: {e}"}, state

    # 7) Format output (only json/raw supported; others fall back)
    fmt = (out_fmt or "json").lower()
    formatted = results if fmt in ("json", "raw") else results

    return {"results": formatted, "error": ""}, state


# --- Registration -----------------------------------------------------------


def register_formulas_calc() -> None:
    register_unit(
        UnitSpec(
            type_name="FormulasCalc",
            input_ports=INPUT_PORTS,
            output_ports=OUTPUT_PORTS,
            step_fn=_formulas_step,
            controllable=True,
            description='Excel-style formulas_calc: execute calculations using the formulas parameter.',
        )
    )
