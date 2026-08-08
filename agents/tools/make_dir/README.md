# TaskVector Tool API Reference: MakeDir

Comprehensive technical documentation for the `make_dir` tool package, detailing its trigger mechanism, workflow execution, and agent follow-up logic.


## 1. Overview

The `make_dir` tool allows the AI agent to create new directories on the filesystem. It is implemented as a modular package that integrates a JSON-based trigger with a canonical workflow execution graph.


## 2. API Specification

### Action Trigger
**Action Name:** `make_dir`
**Description:** Creates a new folder at the specified path.

**JSON Payload:**
```json
{
  "action": "make_dir",
  "path": "/abs/or/rel/<new_folder>"
}
```
**Parameter:**
- `path` (string): The absolute or relative path to the directory to be created. The folder name should be at the tail of the path.


## 3. Technical Implementation

#### Configuration (`tool.yaml`)
- **ID:** `make_dir`
- **Associated Workflow:** `make_dir_workflow.json`

#### Workflow Graph (`make_dir_workflow.json`)
The execution follows a linear path:
1. **Inject Unit (`inject_payload`):** Receives the input payload.
2. **MakeDir Unit (`make_dir`):** Executes the filesystem operation. It has two output ports: `data` (success) and `error` (failure).


## 4. Agent Behavior & Validation

To ensure reliability, the tool utilizes a follow-up mechanism defined in `follow_ups.py`:
- **Pre-verification:** The agent is prompted with: *"IMPORTANT: You requested a new folder creation. You must check the result."*
- **Post-verification:** The agent is instructed to summarize the result of the folder creation for the user before proceeding with subsequent tasks.
