"""
Editable text for system comments added by the normalizer and graph edits.
- Node-RED import: comment shown when a workflow is imported from Node-RED.
- Canonical pipeline: comment shown when a pipeline (RLGym, RLOracle, RLSet, LLMSet) is added.
Edit the constants below to change the messages shown to the user.
"""

# Node-RED import: system comment text (id/commenter/created_at are set in node_red_import.py)
NODE_RED_IMPORT_COMMENT_INFO = """# Units Interaction

The units communicate using JavaScript objects `msg` with a standard structure.

The most common properties are:

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
