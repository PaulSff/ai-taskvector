# Graph code editor (workflow JSON)

Flet UI for editing a **whole** `ProcessGraph` as formatted JSON in the Workflow tab’s **Code** view. It uses a custom serializer so certain regions map to **character ranges**; **Cmd/Ctrl+E** opens a focused overlay for `code_blocks` entries and comment `info` strings (same overlay pattern as `dialog_view_graph_code`).

---

## Layout

| Module | Role |
|--------|------|
| **`graph_code_editor.py`** | `build_graph_code_view`: formatter + block map, main `build_code_editor` JSON surface, toolbar (back, apply, scroll to `todo_list`, copy, chat snippet), selection/cursor watchers, keyboard chaining. |
| **`overlay_editor.py`** | `create_graph_json_overlay`, `get_block_index_from_cursor`: semi-transparent overlay editors and payload read/write for blocks and comments. |
| **`__init__.py`** | Re-exports the public entry points below. |

---

## Public API

Import from `gui.components.workflow_tab.editor.graph_code_editor` (or the submodules directly).

- **`build_graph_code_view(page, graph_ref, *, selection_watch_token_ref, on_graph_saved, show_graph_view, show_toast, chat_panel_api=None)`**  
  Returns the `ft.Column` used as the Code tab body. Caller supplies graph state, navigation back to the graph canvas, async toast helper, and optional chat API (`add_code_reference` for selection → chat).

- **`create_graph_json_overlay(...)`** → `GraphJsonOverlayBundle`  
  Builds the overlay stack, tracks `active_editor` (`"json"` vs `"block"`), and exposes `open_code_editor`, `close_overlay`, etc. Used here and in **`dialogs/dialog_view_graph_code.py`**.

- **`get_block_index_from_cursor(get_selection_range, block_ranges, active_editor)`**  
  Returns the mapped tag under the caret (e.g. `("code_blocks", i)` or comment tags) when the main JSON editor is active.

---

## Formatter and block map

`format_json_with_block_map` walks the graph dict in **key order** and emits pretty JSON with stable `(start, end, tag)` ranges for:

- each **`code_blocks[]`** element;
- **`comments[]`** items with `comment_*` ids (and nested **`info`** sub-ranges where detectable);
- a **single top-level comment object** with `info` / `comment_*` id.

Normal keys are pretty-printed without per-value range tags. A final pass strips empty lines so offsets stay consistent with the displayed text.

---

## Apply (merge keys)

**Apply** parses the editor text as JSON, then merges **`MERGE_GRAPH_KEYS_IF_MISSING`** from the previous graph when those keys are absent (comments, `todo_list`, metadata, origin, runtime, tabs, environments, layout). That avoids losing auxiliary fields on partial paste. The result is passed through **`dict_to_graph`** and **`on_graph_saved`**, then the view switches back to the graph canvas.

---

## Keyboard and UX

- **`create_keyboard_handler`** chains to the page’s previous handler and adds **find** / **escape** for the code editor plus **Cmd/Ctrl+E** → `trigger_edit_code_block` (overlay when the caret sits in a mapped range).
- A small hint (“Use Cmd+E to edit the code”) toggles when the caret is inside a mappable region.
- **Copy** uses the page clipboard + `show_toast`.

---

## Dependencies

- **`gui.utils.code_editor.build_code_editor`** — main JSON and overlay editors.
- **`gui.utils.keyboard_commands.create_keyboard_handler`** — shortcut wiring.
- **`gui.components.workflow_tab.dialogs.dict_to_graph`** — validate and build `ProcessGraph` on apply.

The **visual** graph canvas lives under `workflow/editor/graph_visual_editor/`; this package is only the JSON/code path.
