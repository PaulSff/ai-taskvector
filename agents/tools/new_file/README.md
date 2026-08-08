# Tool: new_file

Detailed technical summary of the `new_file` tool package within the TaskVector framework, designed for programmatic file generation.


## Overview

The `new_file` tool allows the AI agent to create new files in specified directories. It is implemented as a decoupled package where the trigger (prompt), the registration (YAML), and the execution (workflow JSON) are separated to ensure maintainability and consistency.


## Component Breakdown

1. **Configuration (`tool.yaml`)**: Maps the tool ID `new_file` to the execution workflow `new_file_workflow.json`.
2. **Prompt Definition (`prompt.py`)**: Defines the `TOOL_ACTION_PROMPT_LINE`, which instructs the agent on how to format the JSON request. 
3. **Execution Logic (`new_file_workflow.json`)**: A canonical workflow containing two primary units:
   - `inject_payload`: Handles the incoming data template.
   - `generate_new_file`: The core unit responsible for the filesystem operation.


## Usage Schema

To trigger this tool, the agent must provide a JSON object with the following structure:

```json
{
  "action": "new_file",
  "output_dir": "/path/to/dir",
  "file": {
    "output_format": "py",
    "file_name": "filename.py",
    "content": "<string_content>"
  }
}
```


## Workflow

The workflow is defined as a 'coding' environment type. The connection flows from the `inject_payload` unit to the `generate_new_file` unit, ensuring that the payload is correctly processed before the file is written to disk.
