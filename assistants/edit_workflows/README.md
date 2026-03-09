# Edit workflows (Inject → single edit unit)

Each JSON file defines a minimal process graph: **graph_inject** → one edit unit (add_unit, connect, disconnect, etc.). The assistant backend runs the matching workflow per `GraphEdit.action`, injecting the current graph and the edit params, and uses the edit unit’s output as the updated graph for the GUI.

- **inject** node: gets the current graph via executor `initial_inputs` (no upstream connection).
- **edit** node: type = action name; params are set at runtime from the `GraphEdit` object.

Validation and apply logic stay in `assistants/graph_edits.py`; these units only call `apply_graph_edit`. See `assistants/edit_workflow_runner.run_edit_flow`.
