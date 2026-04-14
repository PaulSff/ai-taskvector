"""Prompt line for the graph edit action ``import_workflow`` (load external flow into the canvas)."""

TOOL_ACTION_PROMPT_LINE = (
    '- import_workflow: Load a workflow from the knowledge base or URL: { "action": "import_workflow", '
    '"source": "/.../workflow.json", "origin": "..." }. For URL: { "action": "import_workflow", '
    '"source": "https://...", "merge": "false", "origin": "..." }. '
    "(use only supported origin from the list: node-red, n8n, dict, canonical, pyflow, comfyui, ryven, idaes)\n"
)
