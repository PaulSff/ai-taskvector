"""Workflow Designer / Analyst: JSON action line for formulas_calc."""

TOOL_ACTION_PROMPT_LINE = (
    '- formulas_calc: Perform calcualtions with an .xlsx workbook: '
    '{ "action": "formulas_calc", "path": "/path/to/workbook.xlsx", '
    '"inputs": { "Sheet1!A1": 10, "\'[file.xlsx]Data\'!B2": 2 }, '
    '"outputs": [ "Sheet1!C1", "Data!D4:D6" ], "output_format": "json" }. '
    "Use sheet!cell keys as in Excel; outputs can be single cells or ranges."
)
