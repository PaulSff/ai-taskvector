# GraphDiff unit

Canonical unit that **computes a compact diff** between two graphs (prev vs current) and outputs a changelog string.

- **Inputs**
  - `prev_graph` (Any) — Graph before changes (dict or ProcessGraph). If missing, diff is empty.
  - `current_graph` (Any) — Graph after changes. If missing, diff is empty.
- **Output**
  - `diff` (str) — Human-readable changelog: added/removed units, added/removed connections (e.g. "added foo (Bar); connected a->b").

Used in the assistant workflow so the runner injects only graphs; the workflow produces `recent_changes_block` via this unit instead of an inject.

Implementation delegates to `core.graph.diff.graph_diff()`.
