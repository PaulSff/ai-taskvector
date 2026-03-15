"""
Editable text for system comments added by the normalizer and graph edits.
- Node-RED import: comment shown when a workflow is imported from Node-RED.
- n8n / PyFlow / Ryven / ComfyUI import: comment shown when a workflow is imported from that origin.
- Canonical graph: description of the native process graph (for prompts or when attaching an intro comment).
- Canonical pipeline: comment shown when a pipeline (RLGym, RLOracle, RLSet, LLMSet) is added.
Edit the constants below to change the messages shown to the user.
"""

# Node-RED import: system comment text (id/commenter/created_at are set in node_red_import.py)
NODE_RED_IMPORT_COMMENT_INFO = """# Units Interaction
This is a workflow imported from Node-RED and is supposed to be exported as a Node-RED flow after the modifications.

The units communicate using JavaScript objects `msg` with a standard message structure. The most common properties are:

`msg.payload` - the message body (main data),
`msg.parts` - the message that is split in parts,
`msg.topic` - routing/context,

but the units can have any properties they need.
Find the unit API parameters and additional props in the unit "params": {...}.

## Standard Message Structure

input_port: Any JavaScript object, typically with `payload` property
output_port: Modified message object or array of messages

## Function units

All the function units ("type": "function") are provided with its source code via the `code_blocks`:

  "code_blocks": [
    {
      "id": "unit_id",
      "language": "javascript",
      "source": "any JavaScript code"
    }
  ]
"""

# Canonical (native) graph: description for prompts or intro comment when working with a graph created in-app or loaded as dict/YAML
CANONICAL_GRAPH_COMMENT_INFO = """# Units Interaction
This is a native workflow graph (canonical), created in-app or loaded from dict/YAML.

The units communicate using JSON actions (e.g. { "action": "search", "query": "...", "max_results": "10" }) and its own types for observations (e.g. { "type": "search_result", "results": [...], "query": "..." }). Data flows over connections from port to port; each port carries one of these structured payloads.

## Standard data flow

input_port: Data received on that port
output_port: Data sent from that port

The unit's API parameters live in `params`: {...}, which can be set to adjust its behaviour.

## Function / script units

All the function/script units ("type": "function" or "script") are provided with its source code via the `code_blocks`:

  "code_blocks": [
    { "id": "unit_id", "language": "python", "source": "..." }
  ]
"""

# n8n import: system comment text (id/commenter/created_at are set in n8n_import.py)
N8N_IMPORT_COMMENT_INFO = """# Units Interaction
This is a workflow imported from n8n and is supposed to be exported as an n8n workflow after the modifications.

The units communicate using **items**: each node receives an array of items (JSON objects) and can output items. Connection type (port) distinguishes the kind of data:

`main` – standard item flow (most nodes),
`ai_tool`, `ai_languageModel`, etc. – AI-specific inputs/outputs,

so the same node can have multiple connection types. Unit API and node parameters are in "params": {...}.

## Standard message structure

input_port: Array of items (or single item depending on node type)
output_port: Array of items (or passthrough). Port names/types in input_ports/output_ports match n8n (main, ai_tool, …) for roundtrip.

## Code nodes

Code nodes ("type": "n8n-nodes-base.code") get their source from code_blocks:

  "code_blocks": [
    { "id": "unit_id", "language": "javascript", "source": "..." }
  ]
"""

# PyFlow import: system comment text (id/commenter/created_at are set in pyflow_import.py)
PYFLOW_IMPORT_COMMENT_INFO = """# Units Interaction
This is a workflow imported from PyFlow and is supposed to be exported as a PyFlow graph after the modifications.

The nodes communicate via **pins**: data (Python objects) flows from output pins to input pins. Each pin index corresponds to a port; connections use from_port/to_port. Nodes can have multiple inputs and outputs. Unit API and node data are in "params": {...}.

## Standard data flow

input_port: Data received on that pin (any Python-serializable type)
output_port: Data sent from that pin

## Function / script nodes

Nodes that execute code get their source from code_blocks:

  "code_blocks": [
    { "id": "unit_id", "language": "python", "source": "..." }
  ]
"""

# Ryven import: system comment text (id/commenter/created_at are set in ryven_import.py)
RYVEN_IMPORT_COMMENT_INFO = """# Units Interaction
This is a workflow imported from Ryven and is supposed to be exported as a Ryven project after the modifications.

The nodes communicate by **data flow**: outputs connect to inputs; connection endpoints can be nodeId:port. Data types depend on the node (Python objects, scripts, etc.). Unit API and node data are in "params": {...}.

## Standard data flow

input_port: Data received on that input (port index or name from the flow)
output_port: Data sent from that output

## Script nodes

Nodes that run scripts get their source from code_blocks:

  "code_blocks": [
    { "id": "unit_id", "language": "python", "source": "..." }
  ]
"""

# ComfyUI import: system comment text (id/commenter/created_at are set in comfyui_import.py)
COMFYUI_IMPORT_COMMENT_INFO = """# Units Interaction
This is a workflow imported from ComfyUI and is supposed to be exported as a ComfyUI workflow after the modifications.

The nodes communicate via **typed links**: each link connects an output slot to an input slot. Slot types (e.g. MODEL, LATENT, CONDITIONING, FLOAT) define what flows; connection_type is preserved for roundtrip. Node inputs, outputs, and widgets are in "params": {...}.

## Standard message structure

input_port: Value received on that input slot (type from node's input definition)
output_port: Value sent from that output slot. Port indices match origin_slot/target_slot; link type is in connection_type.

Nodes are identified by class_type (e.g. KSampler, CLIPTextEncode). No code_blocks: ComfyUI nodes are built-in; custom logic lives in separate node definitions.
"""

# Canonical pipeline wiring: used for the system comment when add_pipeline is applied (graph_edits)
# and for the Workflow Designer prompt (assistants/prompts.py)
PIPELINE_WIRING_BASE = (
    "Adhere to the following rules to wire units to the pipeline. "
    "Observation sources → Join; Switch → action targets; Split → simulators (if any)."
)
PIPELINE_WIRING_PREFIX_RLORACLE = "RLOracle Pipeline Wiring Guidelines!"
PIPELINE_WIRING_PREFIX_RLGYM = "RLGym Pipeline Wiring Guidelines!"
PIPELINE_WIRING_PREFIX_RLAGENT = "RLAgent Pipeline Wiring Guidelines!"
PIPELINE_WIRING_PREFIX_LLMAGENT = "LLMAgent Pipeline Wiring Guidelines!"
