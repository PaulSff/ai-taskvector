# n8n built-in node catalog

Built-in n8n node types as an **environment** in our units system. Same idea as `units/pyflow` and `units/node_red`: the assistant can add units from this catalog when the graph has environment `n8n`; they are stored in canonical form and get a JavaScript `code_block` for export (no JS executor in-app yet).

- **Catalog**: `N8N_NODE_CATALOG` — Code, HTTP Request, Schedule Trigger, Switch, Merge, Set, No Operation.
- **Env loader**: `n8n` is registered in `units.env_loaders`; add_environment `n8n` makes these types appear in the Units Library.
- **add_unit**: When the assistant adds a unit whose type is in the catalog and the graph origin is n8n, `graph_edits` attaches the JS template as the unit’s code_block (for export to n8n).

Reference: [n8n built-in node types](https://docs.n8n.io/integrations/builtin/node-types/).
