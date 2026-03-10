# GUI/Chat migration to workflow-driven backend

Plan to migrate the Workflow Designer chat from "direct LLM + parse + apply + follow-ups in Python" to running **assistant_workflow.json** via `run_workflow()` and consuming **merge_response.data**.

---

## Current flow (to replace)

1. **Chat** builds system prompt with `build_workflow_designer_system_prompt(graph_summary, last_apply_result, recent_changes, rag_context)`.
2. **Chat** builds messages with `build_workflow_designer_messages(...)` and calls **LLM directly** (streaming via `llm_client.chat_stream`).
3. **Chat** parses response with `parse_workflow_edits(content)` and runs `handle_workflow_edits_response(content, graph)` → applies edits via `apply_workflow_edits`, returns result/status/graph.
4. **edit_actions_handler.run_workflow_designer_follow_ups** runs follow-up turns: if result has `request_file_content`, `rag_search_results`, `read_code_block_results`, `web_search_results`, `browse_results`, or post-apply (import_workflow, add_comment, TODO), it **calls the LLM again** with that context injected, then `handle_workflow_edits_response` again.

So: prompt built in Python, LLM called directly, parse/apply in handler; follow-ups = more direct LLM calls.

---

## Target flow

1. **Chat** builds **initial_inputs** from current state (user message, graph, turn state, recent_changes, last_edit_block).
2. **Chat** calls **run_workflow(assistant_workflow_path, initial_inputs, unit_param_overrides, format="dict")** (sync or `asyncio.to_thread`).
3. **Chat** reads **outputs["merge_response"]["data"]** → `reply`, `result`, `status`, `graph`, `diff`.
4. **Chat** displays `reply`; if `result["kind"] == "applied"`, updates graph with `result["graph"]`; stores `diff` for next turn’s `inject_recent_changes_block`.
5. **Follow-ups** (Phase 2): if response signals need for file/RAG/web/browse/code_block, GUI fetches that, then **runs the workflow again** with extra injects (or a dedicated follow-up flow).

No `build_workflow_designer_system_prompt`, no direct LLM call, no `handle_workflow_edits_response` for the main turn.

---

## Refactoring steps

### Phase 1: Single-turn workflow run

**1. Define workflow path and runner helper**

- Add a constant or resolver for `assistant_workflow.json` path (e.g. next to `WEB_SEARCH_WORKFLOW_PATH` / `BROWSER_WORKFLOW_PATH` in the handler, or in a small `assistants` or `runtime` helper).
- Add a function that:
  - Takes: `user_message`, `graph`, `turn_state`, `recent_changes_block`, `last_edit_block`, and optional `unit_param_overrides` (llm_agent, rag_search).
  - Builds `initial_inputs`:
    - `inject_user_message.data` = user_message
    - `inject_graph.data` = graph (dict or model_dump)
    - `inject_turn_state.data` = turn_state (e.g. last_apply_result or "Last action: none.")
    - `inject_recent_changes_block.data` = recent_changes_block (str, from previous run’s diff)
    - `inject_last_edit_block.data` = last_edit_block (str, e.g. self-correction when last apply failed)
  - Calls `run_workflow(assistant_workflow_path, initial_inputs=..., unit_param_overrides=..., format="dict")`.
  - Returns either full `outputs` or `outputs["merge_response"]["data"]` (and optionally full outputs for debugging).

**2. Map LLM config into unit_param_overrides**

- The chat currently uses `get_llm_provider(assistant="workflow_designer")` and `get_llm_provider_config(...)` to get provider, model, host, etc.
- Build `unit_param_overrides["llm_agent"] = { "model_name": ..., "provider": ..., "host": ... }` from that (and rag_search from settings if needed) so the workflow’s LLMAgent uses the same config.

**3. Replace the main send path in chat.py**

- **Remove:** building system prompt, building messages, calling `llm_client.chat_stream`, parsing content, calling `handle_workflow_edits_response` for the **first** response.
- **Add:**
  - Build `initial_inputs` from `text` (user message), `graph_ref[0]`, `last_apply_result_ref[0]` (for turn_state), `get_recent_changes()` (for recent_changes_block), and last_edit_block if any.
  - Call the new “run assistant workflow” helper (e.g. via `asyncio.to_thread` so the UI stays responsive).
  - Read `response = outputs["merge_response"]["data"]`; set `content = response["reply"]`, `result = response["result"]`, `status = response["status"]`, `graph = response["graph"]`, `diff = response["diff"]`.
  - Display `content` as the assistant message; if `result["kind"] == "applied"`, call `apply_fn(result["graph"])` and store `diff` for the next turn’s `inject_recent_changes_block`.
- **Streaming:** For Phase 1, accept no streaming (show “Thinking…” then full reply). Optionally later: add streaming support in the runtime or a dedicated “streaming” workflow mode.

**4. Turn state and last_apply_result**

- Today `last_apply_result_ref[0]` holds the last apply result (for “Last action: applied/failed” in the prompt). In the workflow, `inject_turn_state` should receive a **string** (e.g. the same “Turn state: Last action: …” line). So either:
  - Build that string in the GUI from `last_apply_result_ref[0]` (same logic as in `build_workflow_designer_system_prompt` state line), or
  - Pass the dict and have the workflow/Prompt template accept it (if the template already gets turn_state as a string, keep building the string in the GUI).

**5. RAG for the first message**

- The workflow already has `inject_user_message` → RagSearch → Filter → FormatRagPrompt → merge_llm (rag_context). So RAG is inside the workflow; no need to call `get_rag_context` in the GUI for the main turn. Ensure `unit_param_overrides["rag_search"]` (and rag_search_action if used) get `persist_dir`, `embedding_model` from settings so the workflow’s RAG works.

**6. Remove or stub follow-ups for Phase 1**

- **Option A:** Remove the call to `run_workflow_designer_follow_ups` for Phase 1; after one workflow run, show the reply and apply the graph. No file/RAG/web/browse/import/comment/TODO follow-up turns.
- **Option B:** Keep the follow-up loop but have it **run the workflow again** with extra injects (see Phase 2). That requires the workflow to expose “request_file_content” etc. in merge_response and the GUI to run again with inject_request_file_content, etc.

Recommendation: **Option A** for Phase 1; add Phase 2 for follow-ups.

**7. Cleanup**

- Once the main path is workflow-driven, remove or narrow:
  - `build_workflow_designer_system_prompt` (no longer used for main turn; keep only if used elsewhere or for follow-ups in Phase 2).
  - `build_workflow_designer_messages` (same).
  - Direct use of `handle_workflow_edits_response` for the **main** turn (keep if still used inside follow-ups in Phase 2).
- Keep `handle_workflow_edits_response` for **web_search** and **browse** if those stay as “run web_search.json / browser.json” from the handler (they already are), unless you move web actions into the main workflow later.

---

### Phase 2: Follow-up runs (optional)

**8. Expose follow-up requests in the workflow**

- ProcessAgent (parser) currently outputs only `edits`. To support follow-ups without extra direct LLM calls, the parser’s output (or a wrapper unit) must expose: `request_file_content`, `rag_search`, `web_search`, `browse_url`, `read_code_block_ids` when present.
- Extend **merge_response** to include optional keys, e.g. `request_file_content`, `rag_search`, `web_search`, `browse_url`, `read_code_block_ids`, and wire the parser (or a unit that splits parser output) into merge_response so the GUI gets one dict with both “reply/result/status/graph/diff” and “what to fetch for next run.”

**9. GUI follow-up loop** — DONE

- After `run_workflow` and reading `merge_response.data`:
  - If `request_file_content`: read files, then run workflow again with `inject_request_file_content.data` = concatenated file content (and possibly inject_last_edit_block with a “file content provided” line).
  - If `rag_search`: run RAG in the GUI (or a small RAG workflow), then run workflow again with `inject_rag_results.data` = formatted RAG text.
  - If `web_search`: run `web_search.json` as today, then run workflow again with `inject_web_search_results.data` = search results.
  - If `browse_url`: run `browser.json`, then run workflow again with `inject_browse_results.data` = page text.
  - If `read_code_block_ids`: resolve from current graph, then run workflow again with `inject_read_code_block_results.data` = code block text.
- That requires the **workflow** to have injects and merge keys for these (e.g. `inject_request_file_content`, `inject_rag_results`, …) and the prompt template to use them when present. So: extend assistant_workflow.json with these injects and merge_llm keys; extend the prompt template; then implement the GUI loop above.

**10. Post-apply follow-ups (import_workflow, add_comment, TODO)**

- Same idea: after an applied run, if the result indicates “had import_workflow” or “had add_comment/TODO,” run the workflow **once more** with `inject_last_edit_block` (or a dedicated “post_apply_message”) set to “Workflow imported; review…” or “Comment added; review…” and the same user message, so the model can produce a follow-up reply. So one extra workflow run with no new injects except the “post-apply” message.

---

## Summary checklist (Phase 1)

- [ ] Add assistant_workflow path and “run assistant workflow” helper (initial_inputs + run_workflow + return merge_response.data).
- [ ] Build unit_param_overrides from LLM and RAG settings.
- [ ] In chat.py: replace “build prompt → stream LLM → parse → handle_workflow_edits_response” with “build initial_inputs → run workflow → read merge_response.data.”
- [ ] Map last_apply_result and get_recent_changes into turn_state and recent_changes_block strings for initial_inputs.
- [ ] Stop calling get_rag_context in the GUI for the main turn (RAG is inside the workflow).
- [ ] For Phase 1: remove or bypass run_workflow_designer_follow_ups; show one reply and apply graph.
- [ ] Remove or narrow build_workflow_designer_system_prompt / build_workflow_designer_messages for the main path.
- [ ] Accept no streaming in Phase 1 (or add later).

Phase 2 can extend merge_response and the workflow with follow-up injects, then implement the GUI follow-up loop and post-apply run.
