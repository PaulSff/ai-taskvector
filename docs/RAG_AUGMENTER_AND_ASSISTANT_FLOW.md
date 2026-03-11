# RAG augmenter and assistant flow

## Current behavior

- **Workflow Designer** gets RAG context built from the **user message** (`get_rag_context(text, "Workflow Designer")`), so it sees workflows/nodes/docs relevant to the query and the hint: "Use file_path, raw_json_path, or id from above for import_workflow / import_unit when applicable."
- After the assistant **applies** an edit, we only trigger the **augmenter** when there was an `import_workflow` edit. Then we run `_unit_docs_and_rag_sync` in the **background** (all units in the graph), show "Applied", and later "Unit docs updated" when done.
- The assistant is **not** given the Units API / UnitSpec format in its system prompt in depth; it relies on the graph summary and on RAG snippets. The graph summary includes each unit's `input_ports` and `output_ports` **from the graph** (set from the registry on add_unit, or enriched from the registry when normalizing imported units with empty ports). So wiring (connect, observation_source_ids, etc.) can still be guesswork for unknown imported node types until unit docs exist and the augmenter has run.

## Options

### A. Always greet and run full augmentation (or “wait for all”)

- Assistant replies with a short greeting; we run augmentation for **all** units in the graph; when done, we either re-prompt the assistant or show “ready” and let the user ask again.
- **Downsides:** Full augmentation can be slow (many units). The assistant still doesn’t have Units API/specs in its system prompt—only RAG. So “wait for all” doesn’t fix awareness; it only improves RAG content for the *next* turn. Latency is poor if we block the reply on augmentation.

### B. Assistant requests specific unit augmentation (recommended)

- Teach the assistant that it can **ask for unit specs for specific units** (by unit id or by type) so that it can wire them properly.
- We run the augmenter **only for those units** (or for the identities that correspond to those unit ids), then update RAG and either:
  - show a toast and let the **next** user message benefit from the new docs, or
  - inject a synthetic “Unit specs for X, Y are ready” and run the assistant again with updated RAG.
- **Advantages:**
  - **Faster:** only 1–3 units instead of the whole graph.
  - **Assistant stays in control:** it can say “I’ve imported the flow; I need specs for the HTTP Request and Function nodes to connect them. Requesting…” and then the next turn has that context.
  - **Clear UX:** “Generating unit docs for HTTP Request, Function…” instead of a long silent job.
  - **Fits “wire properly”:** the assistant knows which units it lacks ports/specs for and requests only those.

## Recommendation

**Prefer B: let the assistant request specific unit augmentation.**

- Add a **protocol** for the assistant to request specs, e.g.:
  - A dedicated edit action: `{"action": "request_unit_specs", "unit_ids": ["id1", "id2"]}` (not applied to the graph; consumed by the app), or
  - A convention in the natural-language reply that the app parses (e.g. “Request unit specs for: id1, id2”).
- **Implementation sketch:**
  1. **Parse** the assistant response for `request_unit_specs` (or equivalent). If present, after applying any graph edits, compute `identities_all = graph_to_unit_identities(graph)` and restrict to identities that correspond to units whose `id` is in `request_unit_specs.unit_ids` (map unit id → unit type → UnitIdentity by type; dedupe).
  2. Call `ensure_unit_docs_for_units(identities_subset, ...)` and then `run_update(...)` for RAG.
  3. Optionally inject a short system or user message for the next turn: “Unit specs for [X, Y] are now in the knowledge base. You can wire them using input_ports / output_ports.”
  4. **Fallback:** If the assistant does not request specs, keep current behavior: optional background full augment only after `import_workflow`, or skip it and let the user ask later (“generate docs for the nodes I added”).
- **Prompt change:** In the Workflow Designer system prompt, add a short note: when the graph contains units that don’t yet have unit docs (e.g. after import_workflow), you can output `request_unit_specs` with the unit ids you need; the system will generate specs for those units so you can wire them correctly on the next turn.

## Implemented (Option B)

- **Protocol:** The assistant can output a JSON block `{"action": "request_unit_specs", "unit_ids": ["id1", "id2"]}` (in addition to or instead of graph edits). Parsed in `assistants.process_assistant._normalize_parsed_to_edits`; returned in workflow `parser_output` as `request_unit_specs` (chat merges into `result.requested_unit_specs`).
- **Targeted augmenter:** `rag.augmenter.identities_for_unit_ids(graph, unit_ids, mydata_dir)` returns the subset of `UnitIdentity` for those unit ids; `_unit_docs_and_rag_sync_for_unit_ids` in the Flet chat runs `ensure_unit_docs_for_units(identities_subset, ...)` then `run_update`.
- **Chat flow:** When `result["kind"] == "applied"` and `result.get("requested_unit_specs")` is non-empty, we run targeted sync in the background (toast: “Unit specs updated”). When applied with no `request_unit_specs` but with an `import_workflow` edit, we still run full augment in background as before. When `result["kind"] == "no_edits"` and `requested_unit_specs` is non-empty, we run targeted sync using the current graph.
- **Prompt:** Workflow Designer system prompt documents the `request_unit_specs` action and when to use it (e.g. after import_workflow when units lack port info).

## Optional: improve “Units API” awareness in the prompt

- Add a **concise** Units API / UnitSpec summary to the Workflow Designer system prompt (e.g. port ordering, `observation_source_ids` / `action_target_ids`, and that unit docs in the knowledge base provide `input_ports` / `output_ports`). That way the assistant knows the *shape* of the API even when RAG hasn’t returned a specific unit yet.
- Keep detailed UnitSpec and wiring examples in RAG and in the “Relevant context from knowledge base” block.
