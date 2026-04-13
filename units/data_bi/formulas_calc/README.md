# FormulasCalc

Load a workbook (Excel or similar), apply input overrides (cell values or named inputs), recalculate formulas using the formulas PyPI library, and return requested output cells in the requested format.

## Purpose

Execute spreadsheet-style calculations inside a canonical Python unit. The unit accepts an action command describing a workbook path, input overrides, and desired outputs; applies overrides into the workbook model; triggers compilation/evaluation; and exposes computed cell values (including ranges) as JSON-serialisable results.

## Interface

Port / Params.  | Direction | Type  | Description
----------------|-----------|-------|--------------
Input           | in        | dict. | action — action command dict. Example: `{"action":"formulas_calc","path":"/excel.xlsx","inputs":{...},"outputs":[...],"output-format":"json"}`.
Input            | in/config | dict  | params fallback — flattened params when action not supplied on the port: `path`, `inputs` (dict), `outputs` (list), output-format (str).
Output         | out       | dict  | results — mapping of requested output keys -> values (scalars or nested lists for ranges), formatted per output-format (default: JSON dict)
Output         | out       | str   | error — error message (empty string when successful). Unit follows the optional error-port convention.

## Behaviour and semantics

- Action command shape (preferred):
    - action: "formulas_calc"
    - path: workbook path (string). If omitted and the formulas API supports it, an in-memory workbook may be created.
    - inputs: dict mapping cell keys / named inputs to values (e.g., "'[excel.xlsx]DATA'!B3": 1 or "'[excel.xlsx]'!INPUT_A": 3). Overrides are applied before recalculation.
    - outputs: list of cell references or ranges to return (e.g., "DATA!C2", "'[excel.xlsx]DATA'!C4", "DATA!A3:A4").
    - output-format: "json" (default) or "raw"; unsupported formats fall back to JSON-like output.
- Input precedence: action dict provided on the "action" input port > unit params (flattened fallback).
- Uses the formulas library (https://pypi.org/project/formulas/) with two supported backends:
    - **Legacy (ExcelCompiler present):** `ExcelCompiler().read(path)`, compile/recalculate on workbook objects, read cells via `sheet.cell(...)` / `cell.value` / `cell.raw_value`.
    - **Modern 1.3.x (ExcelModel only):** `ExcelModel().load(path).finish()`, probe `calculate()` to map user cell keys to solution keys, `from_dict` for overrides, then `calculate()` again; results are read from the solution mapping (Ranges → scalars or nested lists).
    - **Very old Parser-only builds:** best-effort `Parser.read` / `loads` when neither of the above exists.
- Overrides: The unit parses sheet+cell references (e.g., "SHEET!A1", "'[file]SHEET'!B3"), supports ranges (A1:B2), and attempts to set cell.raw_value/value for overrides. If value is iterable for a range, it will map values to range cells when possible.
- Outputs: For single cells returns scalar or None; for ranges returns nested lists (rows x cols). Keys in the results mapping are the original requested output strings.
- Errors: Import/load/apply/compile/evaluate/collect errors are captured and returned via the error output rather than raising.

## Example

**Input action** (on the action port):

{
"action": "formulas_calc",
"path": "/excel.xlsx",
"inputs": {
    "'[excel.xlsx]'!INPUT_A": 3,
    "'[excel.xlsx]DATA'!B3": 1
    },
"outputs": [
    "'[excel.xlsx]DATA'!C2",
    "'[excel.xlsx]DATA'!C4"
    ],
"output-format": "json"
}

**Example output** (results port):
{
"'[excel.xlsx]DATA'!C2": [[10.0]],
"'[excel.xlsx]DATA'!C4": [[4.0]]
}

Error port: "" (empty string indicates success).
