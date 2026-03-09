# Node-RED core node catalog

Built-in Node-RED node types as an **environment** in our units system. Same idea as `units/pyflow`: the assistant can add units from this catalog when the graph has environment `node_red`; they are stored in canonical form and get a JavaScript `code_block` for export (no JS executor in-app yet).

- **Catalog**: `NODE_RED_NODE_CATALOG` — inject, debug, function, change, switch, split, join, template.
- **Env loader**: `node_red` is registered in `units.env_loaders`; add_environment `node_red` makes these types appear in the Units Library.
- **add_unit**: When the assistant adds a unit whose type is in the catalog and the graph origin is node_red, `graph_edits` attaches the JS template as the unit’s code_block (for export to Node-RED).

Reference: [Node-RED core nodes](https://nodered.org/docs/user-guide/nodes).
