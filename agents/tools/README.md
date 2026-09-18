# TaskVector Tool Development Guide

This guide explains how to create and register new tools within the TaskVector framework. Tools are designed as modular components that can be registered into a global registry and triggered via specific action blocks.

## Tool Structure

Each tool should reside in its own directory under `agents/tools/<tool_name>/`. A standard tool implementation consists of the following files:

Create a package directory:

```text
/tools/list_dir -> 
├── __init__.py  # exports the follow-up runner (and helpers if needed)
├── action_block.py # the tool action validation and its registration
├── follow_ups.py # follow-up prompt lines
├── list_dir_workflow.json
├── prompt.py # tool action prompt line
└── tool.yaml # tool config
```

### 1. `tool.yaml`
Defines the tool's metadata and configuration.
- `id`: Unique identifier for the tool.
- `parser_keys`: A list of action strings that this tool is responsible for parsing.
- `workflow`: (Optional) Path to a JSON workflow file associated with the tool.

### 2. `action_block.py`
This is where the tool's input validation and registration happen.
- **Action Blocks**: Create Pydantic models that inherit from `agents.tools.types.ActionBlock`. Each model should define an `expected_action` (matching the keys in `tool.yaml`).
- **Handlers**: Implement functions that process these blocks and append them to the `ParsedActions` object.
- **Registration**: Call `register_tool()` from `agents.tools.registry` at the end of the file. This function links the tool ID, the follow-up execution function, the action block types, and their respective handlers.

### 3. `follow_ups.py`
Contains the core logic for the tool's execution. This is the function passed to `register_tool` as the `follow_up` handler. It manages the actual side effects or computations the tool performs.

### 4. `prompt.py` (Optional)
Contains tool-specific prompts or instructions used by the LLM to understand when and how to use the tool.

- In the tool `prompt.py` create this module-level string
`TOOL_ACTION_PROMPT_LINE`  - one bullet line descibing the JSON `action` the model emits to call the tool.

- Add extra lines for the context (optional):
In the `follow-ups.py`: 
`<TOOL>_FOLLOW_UP_PREFIX` - inserted in the context right above the tool output 
`<TOOL>_FOLLOW_UP_SUFFIX` - inserted in the context below the tool output 

LLM reads it as follows: 

```text
<TOOL>_FOLLOW_UP_PREFIX
---
your tool output
---
<TOOL>_FOLLOW_UP_SUFFIX
```

`<TOOL>_FOLLOW_UP_USER_MESSAGE` - optionally set a custom user message, which is automatically appended for the user each follow-up turn (typically to make the model accomplish the task)

You must add the flag in the tool runner that tells the follow-up chain to use this message instead of dafault one (DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE).

Register the type in `/agents/tools/types.py` as `FOLLOW_UP_EXTRA_<YOUR_TOOL>_FOLLOW_UP = "<your_tool>_follow_up"`

- Register all the prompt lines in the `_WORKFLOW_DESIGNER_TOOL_FRAGMENT_MAP` inside the `follow_up_fragment_overrides.py`


- Insert the tool in the agent prompt `agents/roles/<role>/prompts.py` as `{tool: "your_tool_id"}` (or `{tool:your_tool_id}`). 

Note: Placeholders are expanded at import by
`agents.tools.prompt_lines.expand_tool_action_placeholders` (loads `prompt.py` by path to avoid import cycles).

## Implementation Example:

To implement a new action (e.g., `add_task`):
1. **Define the Model**: In `action_block.py`, create a class `AddTaskActionBlock(ActionBlock)` with fields like `todo_list_id` and `text`.
2. **Create the Handler**: Write a function that converts the block into a `GraphEdit` action.
3. **Register**: Add the tool into a role prompts.py.
4. **Update tool config**: tool.yaml

## Registry Flow

`agents.tools.registry` -> `register_tool()` -> `action_id` to `(ActionBlock, Handler)` -> Used by the framework to parse LLM output into validated objects.
