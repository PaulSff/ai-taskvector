# Workflow storage format and roundtrip (Node-RED, PyFlow, canonical)

This doc answers: **When we import a workflow from Node-RED or PyFlow, how will it be stored?** and how that ties into roundtrip, preview, save path, and layout.

---

## 1. How imported workflows are stored (recommended)

**Short answer: we store a single canonical format (ProcessGraph), optionally extended with layout and origin.**

| Source | After import | Stored format |
|--------|--------------|---------------|
| **Our graph** (created in GUI or loaded from JSON/YAML) | Already canonical | **ProcessGraph** (units, connections, code_blocks) |
| **Node-RED** | Normalized via `to_process_graph(raw, format="node_red")` | **ProcessGraph** (+ optional layout + optional origin blob) |
| **PyFlow** | Normalized via `to_process_graph(raw, format="pyflow")` | **ProcessGraph** (+ optional layout + optional origin blob) |
| **Ryven** | Normalized via `to_process_graph(raw, format="ryven")` | **ProcessGraph** (+ optional layout + optional origin blob) |

So regardless of import source, **the in-memory and persisted “source of truth” is always ProcessGraph** (our canonical schema). We do **not** keep three separate formats in parallel; we normalize once and work from canonical.

- **Why one format:** Training, rewards, and the constructor all consume ProcessGraph. Having one format avoids sync issues and duplicate logic.
- **Roundtrip:** To re-export to Node-RED or PyFlow we either:
  - **A)** Build target JSON from ProcessGraph (and optional layout) via an **inverse normalizer** (canonical → node_red / pyflow), or  
  - **B)** Keep an optional **origin blob** (raw Node-RED/PyFlow JSON) and merge our changes (e.g. add RL Agent node, apply layout) when exporting.  
  Option A is simpler long-term; option B preserves every detail (labels, comments, etc.) if we never edit the graph in our GUI.

---

## 2. Storing visual positions (layout)

**Node-RED does not use “special nodes” for position.** In Node-RED flow JSON, each **flow node** has `x` and `y` (and optionally `z` for tab/subflow). Config nodes do not have `x`/`y`. So positions are **per-node properties**, not separate layout nodes.

**Recommended approach: same idea in our schema — store position per unit.**

- **Option A — Layout on ProcessGraph**  
  Add an optional field to the canonical schema, e.g.  
  `layout: dict[str, {"x": float, "y": float}] | None`  
  keyed by `unit_id`. When present, the GUI uses it; when absent, we use the existing layered auto-layout. On import from Node-RED/PyFlow we can populate `layout` from each node’s `x`/`y` (and from PyFlow’s position fields if they exist).

- **Option B — Separate “workflow document”**  
  Keep ProcessGraph as topology-only; store a sibling object (e.g. `WorkflowDoc`) with `graph: ProcessGraph`, `layout: {...}`, and optional `origin_format` / `origin_blob`. Same idea, but layout lives outside the graph schema.

Recommendation: **Option A** — optional `layout` on ProcessGraph (or a small `Layout` model referenced by ProcessGraph). That way one JSON file can hold both topology and positions; no need for “special nodes” like in some older editors.

**Concrete schema addition (optional, non-breaking):**

- On **ProcessGraph**:  
  `layout: dict[str, NodePosition] | None = None`  
  with `NodePosition = {"x": float, "y": float}` (and later we can add `z` or tab id if we support subflows).
- On **import** from Node-RED/PyFlow: normalizer maps each node’s `x`/`y` into `layout[node_id]`.
- **Canvas:** If `graph.layout` is present, use it for initial positions; when the user drags a node, update `graph.layout[unit_id]` and persist. If `layout` is missing, keep using `get_graph_layout_for_canvas(graph)` (layered layout).

---

## 3. Summary: storage format by scenario

| Scenario | What we store |
|----------|----------------|
| **Import Node-RED** | ProcessGraph (units, connections, code_blocks) + optional layout (from node x/y) + optional origin_format `"node_red"` and origin_blob (raw JSON) for lossless re-export |
| **Import PyFlow** | Same: ProcessGraph + optional layout + optional origin |
| **Import our JSON/YAML** | ProcessGraph only (and layout if we added it when saving) |
| **User edits in GUI** | ProcessGraph (and layout when we persist drag positions) |

So: **everything is stored as ProcessGraph (+ optional layout + optional origin).** We do not store “Node-RED format” or “PyFlow format” as the primary; we normalize to canonical and optionally keep the original for roundtrip.

---

## 4. How this fits your four requirements

1. **Accept Node-RED, PyFlow, and our graph on import**  
   Already supported in the import dialog (`to_process_graph(..., format="node_red"|"pyflow"|"dict")`). All paths produce the same **ProcessGraph**; no extra “format” to store beyond optional `origin_format` + `origin_blob` if we want lossless re-export.

2. **Preview code of all those workflows in the editor**  
   Today the code view only shows **our** graph JSON (ProcessGraph). To “preview” Node-RED or PyFlow we need either:  
   - **A)** Show the **original** JSON (only possible if we kept `origin_blob` on import), or  
   - **B)** **Serialize ProcessGraph to Node-RED/PyFlow shape** (inverse normalizer) and show that in the editor.  
   So we need at least one of: store `origin_blob`, or implement canonical → node_red / canonical → pyflow serializers. Preview could offer a dropdown: “View as: Canonical | Node-RED | PyFlow”.

3. **Save path (e.g. `/config/my_workflows/my_workflow.json`)**  
   A **settings** component (e.g. Settings icon in the left column opening a settings tab) can store a “workflow save directory” or “default save path”. The path is persisted in app settings (e.g. `settings.json` or a small `settings.py` / config module). Save then writes ProcessGraph (and layout if we add it) to e.g. `{saved_path}/my_workflow.json`. No change to **storage format** — still ProcessGraph.

4. **Store visual positions**  
   As above: add optional **layout** (per-unit `x`, `y`) to the schema; use it in the canvas and persist it when saving. Same approach as Node-RED (position on each node), but we keep it in one place (`layout`) rather than duplicating on each Unit.

---

## 5. Recommendation in one sentence

**Store everything as ProcessGraph (canonical); add optional `layout` (positions per unit_id) and optional `origin_format` + `origin_blob` for roundtrip; use layout on import from Node-RED/PyFlow and when saving after drag; implement preview by either keeping origin_blob or adding inverse normalizers (canonical → node_red / pyflow).**

This gives a single format on disk, preserves positions without “special nodes”, and supports roundtrip and multi-format preview with minimal branching.
