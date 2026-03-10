# UnitsLibrary unit

Canonical unit that builds the **filtered units list** for the Workflow Designer prompt from graph context.

- **Input:** `graph_summary` (dict) — same shape as the Merge key used for the prompt (runtime + environments).
- **Output:** `data` (str) — formatted "Units Library" text (unit types and descriptions filtered by runtime and environment).

Used in the assistant workflow: **inject_graph_summary → UnitsLibrary → Merge** (units_library key). Callers no longer inject `units_library` manually; the unit computes it from `graph_summary` at run time.

Implementation is self-contained in `units/canonical/units_library/library_builder.format_units_library_for_prompt()`. The package exports `format_units_library_for_prompt` for callers (e.g. GUI prompt building) that do not run the graph.
