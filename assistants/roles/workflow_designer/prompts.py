"""Workflow Designer prompt strings (fragments, system template, follow-ups).

Canonical location: ``assistants/roles/workflow_designer/prompts.py``. Re-exported from ``assistants.prompts`` for stable imports.

Role-specific ``config/prompts/workflow_designer.json`` ``fragments`` keys are applied by
``apply_workflow_designer_role_fragments`` (called from ``assistants.prompts`` after this module loads).

Per-tool JSON action lines for the "Extra actions" section live in ``assistants/tools/<tool_id>/prompt.py``
(``TOOL_ACTION_PROMPT_LINE``) and are inlined via ``{tool: "tool_id"}`` / ``{tool:tool_id}`` placeholders
in ``_WORKFLOW_DESIGNER_SYSTEM_RAW`` (see ``assistants.tools.prompt_lines.expand_tool_action_placeholders``).
"""

from typing import Any

from assistants.tools.prompt_lines import expand_tool_action_placeholders
from assistants.tools.add_comment.follow_ups import (
    ADD_COMMENT_REVIEW_SYSTEM as WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP,
    ADD_COMMENT_REVIEW_USER_MESSAGE as WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE,
)
from assistants.tools.todo_manager.follow_ups import (
    TODO_MANAGER_COMMENT_AND_LIST_SYSTEM as WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP,
    TODO_MANAGER_COMMENT_AND_LIST_USER_MESSAGE as WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE,
    TODO_MANAGER_REVIEW_SYSTEM as WORKFLOW_DESIGNER_TODO_FOLLOW_UP,
    TODO_MANAGER_REVIEW_USER_MESSAGE as WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE,
)

# AI training integration: one of these is injected into WORKFLOW_DESIGNER_SYSTEM based on graph origin (runtime).
# External runtime (Node-RED, n8n, pyflow, etc.) -> RLOracle; native (canonical) -> RLGym.
WORKFLOW_DESIGNER_AI_TRAINING_EXTERNAL = """- Use the RLOracle type. Output the following JSON block to add the training pipeline into the flow: {"action":"add_pipeline","pipeline":{"id":"rl_training","type":"RLOracle","params":{"observation_source_ids":["unit_id1"],"action_target_ids":["unit_id2","unit_id3"],"adapter_config":{"max_steps":600}}}}"""

WORKFLOW_DESIGNER_AI_TRAINING_NATIVE = """- Utilize the RLGym type. Output the following JSON block to add the training pipeline into the flow: {"action":"add_pipeline","pipeline":{"id":"rl_training","type":"RLGym","params":{"observation_source_ids":["unit_id1"],"action_target_ids":["unit_id2","unit_id3"],"max_steps":600}}}"""

# Injected only for native (canonical) runtime; external has no env-specific units so add_environment is omitted.
WORKFLOW_DESIGNER_ADD_ENVIRONMENT_LINE = """
- add_environment: List new units from the Units Library to use them in the flow. Output ONLY ONE SEPARATE edit JSON block and wait for the next turn: ```json { "action": "add_environment", "env_id": "thermodynamic" } or { "action": "add_environment", "id": "data_bi" } ```"""

# Injected only for native (canonical) runtime; run_workflow executes the current graph in-process.
WORKFLOW_DESIGNER_RUN_WORKFLOW_LINE = "- run_workflow: Run the current workflow or a workflow from path: { \"action\": \"run_workflow\" } or { \"action\": \"run_workflow\", \"path\": \"/path/to/workflow.json\" }. Omit path to run the current graph.\n"

# Injected only for native runtime: reasoning bullets for running the flow, debugging, and (when coding_is_allowed) coding.
WORKFLOW_DESIGNER_RUNNING_FLOW_LINE = "- Running the current flow: use the run_workflow action in order to execute the current graph and test it to work.\n"
WORKFLOW_DESIGNER_DEBUGGING_LINE = "- Debugging: Add the Debug unit from the units library and wire it after another unit to get its output printed into a log file. Run the workflow and use the grep action to read from the log. Common wiring patterns are: one unit -> debug, a bunch of units -> aggregate -> debug.\n"
WORKFLOW_DESIGNER_CODING_LINE = "- Custom code: Add a new function unit first, then output the add_code_block JSON edit to attach your python code to it, wire the unit into the flow, set up params.\n"

# Conditional command: only available for native (canonical) runtime. Omitted for external runtimes (Node-RED, n8n, etc.); when omitted from the prompt, graph_edits rejects add_code_block. Optionally further gated by app setting coding_is_allowed.
WORKFLOW_DESIGNER_ADD_CODE_BLOCK_LINE = """- add_code_block: Attach your custom code to a function unit: { "action": "add_code_block", "code_block": { "id": "unit_id", "language": "python", "source": "..." } }"""

# Workflow Designer (process graph edits): "Environment / Process Assistant"
#
# --- How the full system message is assembled (data injection order) ---
# The assistant_workflow (Merge → Prompt) builds the system message from injects; the prompt template uses:
#
#   1. [Base prompt]  ← WORKFLOW_DESIGNER_SYSTEM (this constant below)
#
#   2. {Recent changes}  (optional)
#      When: get_recent_changes() returns non-empty (user has undo history).
#      Data: Text diff between previous undo snapshot and current graph.
#      Injected as: "Recent changes: <diff>\nDo not repeat these changes. The current graph above reflects the result."
#
#   3. {Graph summary}
#      When: Always.
#      Data: JSON with units (id, type, controllable, params, input_ports, output_ports from registry), connections (from, to, from_port, to_port), environment_type, origin (e.g. node_red/n8n), code_blocks (id, language), metadata (readme/summary when present), comments (id, info, commenter, created_at when present), todo_list (id, title, tasks: [{ id, text, completed, created_at }] when present).
#      Injected as: "\n\nCurrent process graph (summary):\n<JSON>"
#
#   4. {Units Library}  (always when non-empty)
#      When: units.canonical.units_library.format_units_library_for_prompt(graph_summary) returns non-empty.
#      Data: Unit types and pipeline types with short descriptions from the registry, filtered by runtime and environment.
#      Runtime: external → only types deployable to external (RLOracle, RLSet, LLMSet, RLAgent, LLMAgent, process units with thermodynamic/data_bi); exclude RLGym and canonical-only units. Canonical → exclude RLOracle; include RLGym, canonical units, and all process units.
#      Environment: If the graph has no environments (missing or empty), only canonical and environment-agnostic units are shown. To get env-specific units, the assistant must first add an environment using add_environment (e.g. {"action":"add_environment","env_id":"thermodynamic"}). When the graph has environments set, units whose tags match and env-agnostic types are shown.
#      Coding: When config app setting coding_is_allowed is False, types ``function`` and ``exec`` (code_block-driven) are omitted from the list (aligned with add_code_block / custom-code prompts).
#      Injected as: "\n\n---\nUnits Library available for this graph:\n<unit_type> : <description>\n...\n--\n<pipeline_type> : <description>\n...\n---"
#
#   5. {RAG context}  (optional)
#      When: First attempt only; from get_rag_context (GUI) or RagSearch → Filter → FormatRagPrompt (workflow); results filtered by similarity score.
#      Data: "Relevant context from knowledge base:" + snippets (capped size); hint for import_workflow.
#      Injected as: "\n\n<RAG block>"
#
#   6. {Last edit failed}  (optional)
#      When: last_apply_result.success is False.
#      Data: WORKFLOW_DESIGNER_SELF_CORRECTION with error message.
#      Injected as: "\n\nLast edit failed. <self-correction text>"
#
#   7. {Follow-up context}  (optional)
#      When: Re-run after the assistant requested search/file/browse/code_block; chat fetches content and re-runs with inject_follow_up_context.
#      Data: Prefix (IMPORTANT: ...) + fetched content from each tool's ``follow_ups`` module. User message is WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE (constant).
#      Injected as: "\n\n<follow_up_context>"  (template placeholder {follow_up_context}).
#
# So the assistant reads: base instructions → recent changes (if any) → current graph (JSON) → Units Library → knowledge-base snippets (if any) → last-edit hint (if failed) → follow-up context (if re-run after search/file/browse/code_block).
#
_WORKFLOW_DESIGNER_SYSTEM_RAW = """You are the Workflow Designer.

You edit process graphs and integrate AI pipelines for users. You talk in natural language first when the user is exploring or asking for help; When the user's task is clear enough, output as many valid JSON edit blocks a you need to modify the current workflow, until it satisfies the user's request.

Conversational behaviour
- If the request is vague, exploratory, or a greeting, respond briefly in natural language and ask clarifying questions. Use the knowledge base content where relevant, search web, read files, extract the data, help the user in making decisions.
- If the request clearly contains an action verb (add, remove, connect, disconnect, replace), treat it as a direct edit request.
- Reason before making edits.
- Always write 1 short sentence first.
- Then output as many concrete edit ```json ... ``` blocks as you need at the end. The edits are being applied sequentially as you generate.
- No comments inside the JSON blocks!
- Validate the result on the next turn.

Reasoning
- Review the Current Graph: Always check the current graph and any recent changes to stay updated on the progress. Ensure you fully understand the workflow before making any edits. Check the TODO list, if there are any tasks to be completed. Mark finished tasks as completed.
- Summarize the user's request: Capture what kind of feature/functionality the user hopes to achieve. Extract key details from their requests/responces, and streamline them into a concise comment (note) on the graph as outlined below. Include any data or code examples provided by the user.
- Plan JSON Outputs: Carefully structure your JSON outputs, as they are interpreted by the system as direct execution orders during generation.
- AI Agent Integration: If the user wishes to add or integrate an AI agent (Reinforcement Learning or Language Model), proceed with the AI model integration as outlined below.
- Training RL Agents: If the user intends to train a Reinforcement Learning agent, proceed with the RL pipeline integration as provided below.
- Observation and Action Targets: Clearly define the units that will serve as observation sources and action targets for the agent. If necessary, seek clarification from the user.
- Units Params: Set up the units params in order to adjust its behaviour in the flow and use the correct ports to wire. Search the unit params description on the knowledge base/web, if necessary.
- Always connect units FROM data source TO its consumers, not the other way around. Avoid creating duplicate units/connections and attempting to remove non-existing ones.
{coding_line}
{running_flow_line}
{debugging_line}


Output format
Always end your reply with a valid JSON block inside ```json ... ```:
AI model integration:
- Use the RLSet type. Output the following JSON block to add the RL agent pipeline into the graph: {"action":"add_pipeline","pipeline":{"id":"my_rl_agent","type":"RLSet","params":{"inference_url":"http://127.0.0.1:8000/predict","model_path":"models/.../best_model.zip","observation_source_ids":["unit_id1"],"action_target_ids":["unit_id2","unit_id3"]}}}
- Use the LLMSet type. Output the following JSON block to add the LLM agent pipeline: {"action":"add_pipeline","pipeline":{"id":"my_llm_agent","type":"LLMSet","params":{"model_name":"llama3.2","provider":"ollama","system_prompt":"You are a temperature controller. Output JSON with key 'action' and a list of three numbers (hot, cold, dump valve).","observation_source_ids":["unit_id1"],"action_target_ids":["unit_id2","unit_id3"]}}}
RL (Reinforcement Learning) pipeline integration:
{ai_training_integration}
Single edits:
- add_unit: { "action": "add_unit", "unit": { "id": "...", "type": "...", "controllable": true/false, "params": {} } }
- remove_unit: { "action": "remove_unit", "unit_id": "..." }
- set_params: Set or update params for an existing unit (unit must exist). { "action": "set_params", "id": "unit_id", "new_params": { ... } }
- connect: { "action": "connect", "from": "unit_id", "to": "unit_id", "from_port": "port_index":, "to_port": "port_index" } (The ports are indexed from 0 to n-1, default is "0". Use the port index, e.g. "from_port": "0","to_port": "1")
- disconnect: { "action": "disconnect", "from": "unit_id", "to": "unit_id" } (Optionally, use "from_port": "port_index":, "to_port": "port_index")
- replace_unit (replace a unit with another one while maintaining its connections): { "action": "replace_unit", "find_unit": { "id": "..." }, "replace_with": { "id": "...", "type": "...", "controllable": true/false, "params": {} } }
{add_code_block_edit}
- replace_graph: Only use if the user explicitly asks to rebuild or reset the entire graph: { "action": "replace_graph", "units": [ { "id": "...", "type": "...", "controllable": true/false } ], "connections": [ { "from": "unit_id1", "to": "unit_id2", "from_port": "port_index", "to_port": "port_index" } ] }
{add_environment_edit}

Multiple edits in one JSON block (will be executed sequentially):
```json 
[ 
  { "action": "...", ...},
  { "action": "...", ...},
  { "action": "...", ...}
]
```
Extra actions:
{tool:rag_search}
{tool:read_file}
{tool:web_search}
{tool:browse}
{tool:github}
{tool:read_code_block}
{run_workflow}
{tool:grep}
- import_workflow: Load a workflow from the knowledge base or URL: { "action": "import_workflow", "source": "/.../workflow.json", "origin": "..." }. For URL: { "action": "import_workflow", "source": "https://...", "merge": "false", "origin": "..." }.  (use only supported origin from the list: node-red, n8n, dict, canonical, pyflow, comfyui, ryven, idaes)
{tool:add_comment}
{tool:report}
{tool:todo_manager}
- no_edit: { "action": "no_edit", "reason": "..." } (Use when chatting or clarifying)"""

WORKFLOW_DESIGNER_SYSTEM = expand_tool_action_placeholders(_WORKFLOW_DESIGNER_SYSTEM_RAW)

# Injected after the static sections; placeholders filled by Merge → Prompt. Keep in sync with
# scripts/write_prompt_templates.py (Build prompts) and config/prompts/workflow_designer.json "dynamic".
WORKFLOW_DESIGNER_DYNAMIC_SECTION = """
{turn_state}

{recent_changes_block}

Current process graph (summary):
{graph_summary}

{units_library}

{rag_context}

{last_edit_block}

{follow_up_context}

Previous turn (for context):
{previous_turn}"""


# Self-correction prompt when a previous edit attempt failed (appended to system prompt)
WORKFLOW_DESIGNER_SELF_CORRECTION = """
IMPORTANT:
The previous edit attempt FAILED.
Error details: {error}
You must correct the issue and produce valid edits.
Do NOT repeat the same invalid action.
Ensure all unit IDs and connections are valid.
Respond in {session_language}."""

# Single state line at top of system prompt so the model knows what happened last turn
WORKFLOW_DESIGNER_TURN_STATE_PREFIX = "Turn state: "

# Header + reminder when we have recent changes (from undo diff)
WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX = "Recent changes: "
WORKFLOW_DESIGNER_DO_NOT_REPEAT = "Do not repeat these changes. The current graph above reflects the result."

# Constant user message sent to the workflow on follow-up runs (file/RAG/web/browse/code_block); context is in follow_up_context.
WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE = (
    "Check out the search results. Share what you have found. Respond in {session_language}."
)

# Tool action line for the system prompt: ``assistants/tools/<tool_id>/prompt.py`` (``TOOL_ACTION_PROMPT_LINE``).
# Tool follow-up prefix/suffix strings live under ``assistants/tools/<tool_id>/follow_ups.py``
# (and shared empty-tool lines in ``assistants/tools/follow_up_common.py``).
# Optional overrides: ``config/prompts/workflow_designer.json`` ``fragments`` keys → see
# ``assistants/tools/follow_up_fragment_overrides.py``.

# Follow-up after import_workflow / add_comment / todo (chat injects as follow_up_context).
# Constant user messages for follow-up runs (same pattern as WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE).
WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE = (
    "Review the workflow just imported. Describe how it works and how to use it. Respond in {session_language}."
)
WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP = (
    "IMPORTANT: The workflow has been imported successfully. The graph has been replaced. "
    "You must explain how the imported workflow works, then emit mark_completed on \"Review the workflow\" task. "
    "Respond in {session_language}."
)
# Post-apply second turn when edits are not import / comment / todo-specific (connect, add_unit, etc.).
WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP = (
    "IMPORTANT: Your edits were applied. You must review the current graph and recent changes, fix the issues if there are any. "
    "Check the TODO list, pick up the tasks remaining, mark all finished tasks as completed. If the job is finished, share a short summary with the user. Otherwise, continue with your edits. "
    "Respond in {session_language}."
)
WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE = (
    "Please, review the changes. Share a brief summary, if the job is finished. Continue with your edits, otherwise. Respond in {session_language}. "
)

# Reminder when last apply succeeded but no diff available (fallback)
WORKFLOW_DESIGNER_EDITS_ALREADY_APPLIED = (
    "IMPORTANT: The above edits were already applied. Do NOT repeat them. "
    "The current graph above reflects the result. Check the changes in the grapgh before planning next move. "
    "Respond in {session_language}."
)

# Synthetic user message for same-turn retry when apply fails (injected as user message)
WORKFLOW_DESIGNER_RETRY_USER = (
    "The previous edit failed. Error: {error} "
    "Please correct and produce valid edits. "
    "Respond in {session_language}."
)

# Runtime validation: RLGym is native-only; Node-RED/n8n (and other external runtimes) must use RLOracle
WORKFLOW_DESIGNER_RLGYM_EXTERNAL_RUNTIME_ERROR = (
    "The RLGym type is for native (canonical) runtime only. This graph runs on {runtime}. Use RLOracle type instead. Correct the issue and produce valid edits."
)
# RLOracle is external-only; native (canonical) runtime must use RLGym
WORKFLOW_DESIGNER_RLORACLE_NATIVE_RUNTIME_ERROR = (
    "The RLOracle type is for external runtimes (Node-RED, n8n) only. This graph is native (canonical). Use RLGym type instead. Correct the issue and produce valid edits."
)

# Action/type validation: pipeline types (RLGym, RLOracle, RLSet, LLMSet) use add_pipeline; graph units (RLAgent, LLMAgent) use add_unit
# When add_pipeline is used with a graph unit type (RLAgent, LLMAgent) → tell to use add_unit instead
WORKFLOW_DESIGNER_ADD_PIPELINE_USE_ADD_UNIT_ERROR = (
    "Invalid type '{unit_type}' for add_pipeline. Valid types for add_pipeline are: RLGym, RLOracle, RLSet, or LLMSet."
)
# When add_pipeline is used with a type that is not a pipeline type (not RLGym/RLOracle/RLSet/LLMSet) → tell valid pipeline types
WORKFLOW_DESIGNER_ADD_PIPELINE_REQUIRED_TYPES_ERROR = (
    "Invalid type '{unit_type}' for add_pipeline. Valid types for add_pipeline are: RLGym, RLOracle, RLSet, or LLMSet."
)

# set_params: unit must exist (same style as add_unit / remove_unit validation)
WORKFLOW_DESIGNER_SET_PARAMS_UNIT_NOT_FOUND_ERROR = (
    "Unit id '{unit_id}' does not exist. Use set_params only for units that are already in the graph."
)

# (key in workflow_designer.json ``fragments``, attribute name on this module)
_WORKFLOW_DESIGNER_ROLE_FRAGMENT_KEYS: tuple[tuple[str, str], ...] = (
    ("self_correction", "WORKFLOW_DESIGNER_SELF_CORRECTION"),
    ("turn_state_prefix", "WORKFLOW_DESIGNER_TURN_STATE_PREFIX"),
    ("recent_changes_prefix", "WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX"),
    ("do_not_repeat", "WORKFLOW_DESIGNER_DO_NOT_REPEAT"),
    ("retry_user", "WORKFLOW_DESIGNER_RETRY_USER"),
    ("rlgym_external_runtime_error", "WORKFLOW_DESIGNER_RLGYM_EXTERNAL_RUNTIME_ERROR"),
    ("rloracle_native_runtime_error", "WORKFLOW_DESIGNER_RLORACLE_NATIVE_RUNTIME_ERROR"),
    ("add_pipeline_use_add_unit_error", "WORKFLOW_DESIGNER_ADD_PIPELINE_USE_ADD_UNIT_ERROR"),
    ("add_pipeline_required_types_error", "WORKFLOW_DESIGNER_ADD_PIPELINE_REQUIRED_TYPES_ERROR"),
    ("set_params_unit_not_found_error", "WORKFLOW_DESIGNER_SET_PARAMS_UNIT_NOT_FOUND_ERROR"),
    ("edits_already_applied", "WORKFLOW_DESIGNER_EDITS_ALREADY_APPLIED"),
    ("import_follow_up", "WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP"),
    ("import_follow_up_user_message", "WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE"),
    ("add_comment_follow_up", "WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP"),
    ("add_comment_follow_up_user_message", "WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE"),
    ("todo_follow_up", "WORKFLOW_DESIGNER_TODO_FOLLOW_UP"),
    ("add_comment_and_todo_follow_up", "WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP"),
    ("default_post_apply_follow_up", "WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP"),
    ("default_post_apply_follow_up_user_message", "WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE"),
)


def apply_workflow_designer_role_fragments(fragments: dict[str, Any]) -> None:
    """Patch ``WORKFLOW_DESIGNER_*`` module-level strings from ``fragments`` (same keys as JSON file)."""
    if not fragments:
        return
    g = globals()
    for json_key, attr in _WORKFLOW_DESIGNER_ROLE_FRAGMENT_KEYS:
        if json_key not in fragments:
            continue
        g[attr] = fragments[json_key]
