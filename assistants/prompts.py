"""
System prompts and fragment constants for Workflow Designer and RL Coach assistants.

**Where this module is used (current implementation):**

- **Workflow Designer (Flet chat, workflow-driven):** The *main* system prompt is **not** built here.
  It comes from **config/prompts/workflow_designer.json**: the assistant_workflow's Prompt unit loads
  that file (template_path from app settings) and fills placeholders from Merge (graph_summary,
  units_library, rag_context, turn_state, etc.). This module only supplies the **fragment constants**
  used to build the *values* injected into the workflow: turn_state string, last_edit_block,
  recent_changes_block (workflow_designer_handler), and follow-up message prefixes/suffixes (chat.py).
  **Edit those strings in this module** (defaults). Optionally, a `fragments` object in
  workflow_designer.json can override the same keys at import time for deployments that prefer JSON;
  if `fragments` is absent, Python-only defaults apply.

- **RL Coach (Flet chat):** The Prompt unit loads **config/prompts/rl_coach.json** (template_path from settings).
  The canonical text is **RL_COACH_SYSTEM** + **RL_COACH_DYNAMIC_SECTION** in this module; run
  **Build prompts** (or `scripts/write_prompt_templates.py`) to refresh the JSON after editing here.

- **scripts/write_prompt_templates.py:** Uses WORKFLOW_DESIGNER_* and RL_COACH_* as the *source* to
  generate/update config/prompts/workflow_designer.json and rl_coach.json. Python constants are the
  source of truth for *writing* the JSON; at runtime the assistants load those JSON files.

- **core/graph/graph_edits.py:** Error message strings (WORKFLOW_DESIGNER_ADD_PIPELINE_*_ERROR).

- **report action (ProcessAgent):** Regular extra action in the workflow designer list; Report unit consumes parser_output["report"] and writes report.md/report.csv.

Use get_fragment(template_name, fragment_key, **kwargs) to format a fragment from the JSON (e.g. self_correction
with error=...) for injection into Merge or backward-compatible use.
"""

import json
from pathlib import Path

# Workflow Designer prompt content comes from config/prompts/workflow_designer.json (workflow Merge → Prompt).
# Pipeline wiring text for add_pipeline comments lives in core.normalizer.system_comments (used by graph_edits only).

_PROMPTS_DIR = Path(__file__).resolve().parent.parent / "config" / "prompts"


def _section_content(item: object) -> str:
    """Extract content from a section: string or dict with 'content' key."""
    if isinstance(item, dict) and "content" in item:
        c = item["content"]
        return c if isinstance(c, str) else ""
    return item if isinstance(item, str) else ""


def _load_template_from_json(name: str) -> str:
    """Load template string from config/prompts/<name>.json ('template' or assembled from 'sections')."""
    path = _PROMPTS_DIR / name
    if not path.exists():
        return ""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return ""
        template = data.get("template")
        if isinstance(template, str) and template.strip():
            return template
        sections = data.get("sections")
        if isinstance(sections, list) and sections:
            return "\n\n".join(_section_content(s).strip() for s in sections if _section_content(s).strip())
        return ""
    except (OSError, json.JSONDecodeError, TypeError):
        return ""


def _load_fragments(name: str) -> dict[str, str]:
    """Load fragments dict from config/prompts/<name>.json (key 'fragments'). Used for self-correction, errors, follow-ups."""
    path = _PROMPTS_DIR / (name if name.endswith(".json") else name + ".json")
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {}
        frag = data.get("fragments")
        return frag if isinstance(frag, dict) else {}
    except (OSError, json.JSONDecodeError, TypeError):
        return {}


def get_fragment(template_name: str, fragment_key: str, **kwargs: str) -> str:
    """Load a fragment from template JSON and substitute placeholders (e.g. error=..., runtime=..., unit_type=...). For use in Merge → Prompt pipeline."""
    fragments = _load_fragments(template_name)
    template = fragments.get(fragment_key, "")
    if not template:
        return ""
    try:
        return template.format(**kwargs)
    except KeyError:
        return template

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
#      Data: Prefix (IMPORTANT: ...) + fetched content. User message is WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE (constant). Uses WORKFLOW_DESIGNER_*_FOLLOW_UP_* constants.
#      Injected as: "\n\n<follow_up_context>"  (template placeholder {follow_up_context}).
#
# So the assistant reads: base instructions → recent changes (if any) → current graph (JSON) → Units Library → knowledge-base snippets (if any) → last-edit hint (if failed) → follow-up context (if re-run after search/file/browse/code_block).
#
WORKFLOW_DESIGNER_SYSTEM = """You are the Workflow Designer.

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
- Refine the goal and summarize: Capture what kind of feature/functionality the user hopes to achieve. Extract key details from their requests/responces, and streamline them into a concise comment (note) on the graph as outlined below. Include any data or code examples provided by the user.
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
- search: Search on the knowledge base (workflows, docs, etc.): { "action": "search", "query": "...", "max_results": "10" }
- read_file: Read file content from the knowledge base: { "action": "read_file", "path": "e.g. /abs/path/to/file.csv" }
- web_search: Search on the web with DuckDuckGo: { "action": "web_search", "query": "...", "max_results": "10" }
- browse: Read a web page (HTML/URL): { "action": "browse", "url": "https://..." } (url required).
- github: Query GitHub: { "action": "github", "payload": { "action": "github_search_repos", "q": "topic:workflow" } }. payload.action can be: github_search_repos, github_search_code, github_search_issues, github_get_repo, github_get_content, github_get_readme, github_list_releases, github_list_commits. Include in payload the params for that action (e.g. q, owner, repo, path, ref, per_page).
- read_code_block: Only if you lack information, request the source of a code block from the graph: { "action": "read_code_block", "id": "unit_id" }. A todo task "Review the source {unit_id}" is added; the source is then included in the graph summary until the task is completed or removed.
{run_workflow}
- grep: Search inside a file content or raw text (e.g. logs): { "action": "grep", "pattern": "...", "source": "path or text" }. source = file path (e.g. log.txt) or inline text; omit to use upstream input.
- import_workflow: Load a workflow from the knowledge base or URL: { "action": "import_workflow", "source": "/.../workflow.json", "origin": "..." }. For URL: { "action": "import_workflow", "source": "https://...", "merge": "false", "origin": "..." }.  (use only supported origin from the list: node-red, n8n, dict, canonical, pyflow, comfyui, ryven, idaes)
- add_comment: Leave a useful note on the graph: { "action": "add_comment", "info": "...", "commenter": "Workflow Designer" }
- report: Generate a structured summary for the user and save it as a file: { "action": "report", "output_format": "md" | "csv", "text": { ... } }. Formatting: MD: { "title", "summary", "sections": [{ "heading", "body" }] }; CSV: { "headers": [...], "rows": [[...], ...] }.
- no_edit: { "action": "no_edit", "reason": "..." } (Use when chatting or clarifying)
- TODO list edit actions:
  - add_todo_list: { "action": "add_todo_list", "title": "My new todo list" }
  - remove_todo_list: { "action": "remove_todo_list" }
  - add_task: { "action": "add_task", "text": "task description..." }
  - remove_task: { "action": "remove_task", "task_id": "..." }
  - mark_completed: { "action": "mark_completed", "task_id": "...", "completed": true } (completed defaults to true)"""

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

# Follow-up prefix/suffix (self-correction style): chat injects content into follow_up_context.
WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX = "IMPORTANT: You requested a file content. You must check the content.\n\n"
WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX = "\n\nRespond in {session_language}."
# Code-block follow-up: source is in graph summary (not injected); chat adds todo "Review the source {unit_id}".
WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_PREFIX = "IMPORTANT: You requested code block(s) from the graph. You must check the code.\n\n"
WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_SUFFIX = "\n\nRespond in {session_language}."
# Separate user message for code-block follow-up runs; {unit_ids} is replaced with the requested unit id(s) (e.g. "fn_1, exec_2").
WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE = (
    "Check out the code blocks in the graph summary: {unit_ids}. Keep going with your edits."
    "Respond in {session_language}."
)

WORKFLOW_DESIGNER_RAG_FOLLOW_UP_PREFIX = "IMPORTANT: You requested the RAG search. You must check the search results.\n\n"
WORKFLOW_DESIGNER_RAG_FOLLOW_UP_SUFFIX = "\n\nRespond in {session_language}."
WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_PREFIX = "IMPORTANT: You requested the web search. You must check the search results.\n\n"
WORKFLOW_DESIGNER_WEB_SEARCH_FOLLOW_UP_SUFFIX = "\n\nRespond in {session_language}."
WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_PREFIX = "IMPORTANT: You requested the web page content from a URL. You must check the page content.\n\n"
WORKFLOW_DESIGNER_BROWSE_FOLLOW_UP_SUFFIX = "\n\nRespond in {session_language}."
WORKFLOW_DESIGNER_GITHUB_FOLLOW_UP_PREFIX = "IMPORTANT: You requested GitHub data. You must check the result.\n\n"
WORKFLOW_DESIGNER_GITHUB_FOLLOW_UP_SUFFIX = "\n\nRespond in {session_language}."

WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_PREFIX = "IMPORTANT: You requested to run the workflow. You must check the run result.\n\n"
WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_SUFFIX = "\n\nRespond in {session_language}."
WORKFLOW_DESIGNER_GREP_FOLLOW_UP_PREFIX = "IMPORTANT: You requested a grep search. You must check the result.\n\n"
WORKFLOW_DESIGNER_GREP_FOLLOW_UP_SUFFIX = "\n\nRespond in {session_language}."

# Injected as the body of follow_up_context when a tool ran but returned no usable data (or failed in chat).
WORKFLOW_DESIGNER_TOOL_EMPTY_RESULT_LINE = "(Nothing found: no data was returned for this request.)"
# User message for that same follow-up workflow run (replaces WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE for empty-tool turns).
WORKFLOW_DESIGNER_TOOL_EMPTY_USER_MESSAGE = (
    "Nothing usable was returned for your last request. Check the status and continue with your edits, if suitable. Otherwise, share the summary. "
    "Respond in {session_language}."
)

# Follow-up after import_workflow / add_comment / todo (chat injects as follow_up_context).
# Constant user messages for follow-up runs (same pattern as WORKFLOW_DESIGNER_FOLLOW_UP_USER_MESSAGE).
WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE = (
    "Review the workflow just imported. Describe how it works and how to use it. Respond in {session_language}."
)
WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP_USER_MESSAGE = "Review your comment and continue. Respond in {session_language}."
WORKFLOW_DESIGNER_TODO_FOLLOW_UP_USER_MESSAGE = (
    "Review the TODO list and continue. Respond in {session_language}."
)
WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP_USER_MESSAGE = (
    "Review your comment and the TODO list. Respond in {session_language}."
)

WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP = (
    "IMPORTANT: The workflow has been imported successfully. The graph has been replaced. "
    "You must explain how the imported workflow works, then emit mark_completed on \"Review the workflow\" task. "
    "Respond in {session_language}."
)
WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP = (
    "IMPORTANT: Your comment was added. You must review the comment. Respond in {session_language}."
)
WORKFLOW_DESIGNER_TODO_FOLLOW_UP = (
    "IMPORTANT: The TODO list has been updated. You must review the TODO list. Respond in {session_language}."
)
WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP = (
    "IMPORTANT: Your comment and the TODO list have been updated. "
    "You must review the comment and TODO list. Respond in {session_language}."
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

# Optional override: workflow_designer.json "fragments" (if present) replaces matching keys below.
# Default source of truth for these strings is this file, not JSON.
_WF_FRAGMENTS = _load_fragments("workflow_designer.json")
if _WF_FRAGMENTS:
    if "self_correction" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_SELF_CORRECTION = _WF_FRAGMENTS["self_correction"]
    if "turn_state_prefix" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_TURN_STATE_PREFIX = _WF_FRAGMENTS["turn_state_prefix"]
    if "recent_changes_prefix" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_RECENT_CHANGES_PREFIX = _WF_FRAGMENTS["recent_changes_prefix"]
    if "do_not_repeat" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_DO_NOT_REPEAT = _WF_FRAGMENTS["do_not_repeat"]
    if "retry_user" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_RETRY_USER = _WF_FRAGMENTS["retry_user"]
    if "rlgym_external_runtime_error" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_RLGYM_EXTERNAL_RUNTIME_ERROR = _WF_FRAGMENTS["rlgym_external_runtime_error"]
    if "rloracle_native_runtime_error" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_RLORACLE_NATIVE_RUNTIME_ERROR = _WF_FRAGMENTS["rloracle_native_runtime_error"]
    if "add_pipeline_use_add_unit_error" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_ADD_PIPELINE_USE_ADD_UNIT_ERROR = _WF_FRAGMENTS["add_pipeline_use_add_unit_error"]
    if "add_pipeline_required_types_error" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_ADD_PIPELINE_REQUIRED_TYPES_ERROR = _WF_FRAGMENTS["add_pipeline_required_types_error"]
    if "set_params_unit_not_found_error" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_SET_PARAMS_UNIT_NOT_FOUND_ERROR = _WF_FRAGMENTS["set_params_unit_not_found_error"]
    if "edits_already_applied" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_EDITS_ALREADY_APPLIED = _WF_FRAGMENTS["edits_already_applied"]
    if "import_follow_up" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP = _WF_FRAGMENTS["import_follow_up"]
    if "import_follow_up_user_message" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_IMPORT_FOLLOW_UP_USER_MESSAGE = _WF_FRAGMENTS["import_follow_up_user_message"]
    if "add_comment_follow_up" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_ADD_COMMENT_FOLLOW_UP = _WF_FRAGMENTS["add_comment_follow_up"]
    if "todo_follow_up" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_TODO_FOLLOW_UP = _WF_FRAGMENTS["todo_follow_up"]
    if "add_comment_and_todo_follow_up" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_ADD_COMMENT_AND_TODO_FOLLOW_UP = _WF_FRAGMENTS["add_comment_and_todo_follow_up"]
    if "default_post_apply_follow_up" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP = _WF_FRAGMENTS["default_post_apply_follow_up"]
    if "default_post_apply_follow_up_user_message" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE = _WF_FRAGMENTS[
            "default_post_apply_follow_up_user_message"
        ]
    if "request_file_content_follow_up_prefix" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_PREFIX = _WF_FRAGMENTS["request_file_content_follow_up_prefix"]
    if "request_file_content_follow_up_suffix" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_REQUEST_FILE_CONTENT_FOLLOW_UP_SUFFIX = _WF_FRAGMENTS["request_file_content_follow_up_suffix"]
    if "read_code_block_follow_up_prefix" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_PREFIX = _WF_FRAGMENTS["read_code_block_follow_up_prefix"]
    if "read_code_block_follow_up_suffix" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_SUFFIX = _WF_FRAGMENTS["read_code_block_follow_up_suffix"]
    if "read_code_block_follow_up_user_message" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_READ_CODE_BLOCK_FOLLOW_UP_USER_MESSAGE = _WF_FRAGMENTS["read_code_block_follow_up_user_message"]
    if "run_workflow_follow_up_prefix" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_PREFIX = _WF_FRAGMENTS["run_workflow_follow_up_prefix"]
    if "run_workflow_follow_up_suffix" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_RUN_WORKFLOW_FOLLOW_UP_SUFFIX = _WF_FRAGMENTS["run_workflow_follow_up_suffix"]
    if "grep_follow_up_prefix" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_GREP_FOLLOW_UP_PREFIX = _WF_FRAGMENTS["grep_follow_up_prefix"]
    if "grep_follow_up_suffix" in _WF_FRAGMENTS:
        WORKFLOW_DESIGNER_GREP_FOLLOW_UP_SUFFIX = _WF_FRAGMENTS["grep_follow_up_suffix"]

# Create-filename workflow: used by chat to suggest a short snake_case filename from the user's first message.
CREATE_FILENAME_SYSTEM = (
    "You generate concise filenames for chat logs. "
    "Return ONLY a short snake_case name (no spaces), WITHOUT extension. "
    "Use 3-8 words max. Example: workflow_roundtrip_execution"
)

# RL Coach (training config edits): "Training Assistant"
# For reward shaping: direct DSL actions (formula/rules).
RL_COACH_SYSTEM = """You are the RL Coach. You help users configure RL training: goals, rewards, algorithm, and hyperparameters. You talk in natural language first when the user is exploring or asking for help; you only output a concrete JSON edit when they ask for a specific change or agree to a suggestion.

## Conversational behavior
- If the user says hi, asks for help, or the request is vague: respond in a friendly, helpful way. Explain you can: change goals, add/edit reward formula (DSL), add reward rules (if-then), and tune hyperparameters. End with: ```json\n{ "action": "no_edit", "reason": "clarifying with user" }\n```
- Only when the user clearly asks for a specific config change output a concrete edit JSON.

## Reward shaping (DSL actions)
   - Add formula component: { "action": "reward_formula_add", "expr": "...", "weight": -0.1 } or "reward": 10.0 (use weight for numeric term, reward for conditional bonus)
   - Add rule: { "action": "reward_rules_add", "condition": "get(outputs, 'tank.temp', 0) > 50", "reward_delta": -1.0 }
   - Replace formula: { "action": "reward_formula_set", "formula": [ { "expr": "...", "weight": 1.0 }, ... ] }
   - Replace rules: { "action": "reward_rules_set", "rules": [ { "condition": "...", "reward_delta": -1 }, ... ] }

## Reward DSL
- **outputs**: graph unit outputs. Use get(outputs, "unit_id.port", default) to read. Example: get(outputs, "mixer_tank.temp", 0), get(outputs, "dump_valve.flow", 0)
- **goal**: goal config. Use goal.get("target_temp", 37), goal.get("target_volume_ratio")
- **observation**: list of floats. observation[0], observation[i]
- **step_count**, **max_steps**
- Math: abs, min, max, sqrt, etc. Use get() for safe access.
- Formula component: expr (string) + weight (numeric term) OR reward (conditional: add when expr is truthy). Example weight: "-abs(get(outputs, 'tank.temp', 0) - goal.get('target_temp', 37))". Example reward: "get(outputs, 'tank.volume_ratio', 0) >= 0.8 and get(outputs, 'tank.volume_ratio', 0) <= 0.85"

## Other edits (goal, algorithm, hyperparameters)
- Change goal: { "goal": { "target_temp": 40.0 } }
- Change hyperparams: { "hyperparameters": { "learning_rate": 1e-4 } }
- Direct rewards merge: { "rewards": { "formula": [...], "rules": [...] } }

## Output format
Always end your reply with a JSON block inside ```json ... ```.
- No change: { "action": "no_edit", "reason": "..." }

Important: Write 1-2 sentences of natural language first, then the JSON block at the end. Never reply with only JSON."""

# Injected after RL_COACH_SYSTEM in config/prompts/rl_coach.json (Merge → Prompt). Keep in sync with rl_coach_workflow merge keys.
RL_COACH_DYNAMIC_SECTION = """## Current training config (from file)
{training_config}

## Current training results / best model
{training_results}

## Relevant context (RAG)
{rag_context}

## Previous turn
{previous_turn}"""

