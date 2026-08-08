# Delete Tool package

This report provides a detailed breakdown of the 'delete' tool implementation within the TaskVector framework, explaining how the prompt, configuration, and workflow interact to enable safe file and folder deletion.


## Module Overview

The `delete` tool is a specialized module designed to allow the AI agent to perform filesystem deletions. It follows a decoupled architecture where the trigger (prompt), the mapping (config), and the execution (workflow) are separated.


## Component Breakdown

1. **Configuration (`tool.yaml`)**: Maps the `delete` action to the `delete_workflow.json` execution graph.
2. **Prompting (`prompt.py`)**: Defines the strict JSON schema for the agent: `{ "action": "delete", "path": "..." }`.
3. **Verification Logic (`follow_ups.py`)**: Implements a safety mechanism that forces the agent to check the result of the deletion and summarize it for the user, preventing 'silent' failures or accidental deletions.
4. **Execution Graph (`delete_workflow.json`)**: A canonical workflow consisting of an `Inject` unit (payload handling) and a `Delete` unit (filesystem operation).


## Workflow Logic

The workflow is streamlined for reliability:
- **Input**: Receives the target path via the `inject_payload` unit.
- **Process**: The `delete` unit executes the removal of the specified file or folder.
- **Output**: Returns either a success confirmation or a detailed error string, which is then processed by the agent's follow-up logic.


## Conclusion

The module is robustly implemented, ensuring that the agent does not just 'attempt' a deletion but is systematically required to verify the outcome, maintaining high reliability in file management tasks.
