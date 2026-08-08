# Tool: edit_file

Detailed technical overview of the edit_file tool package, focusing on its patch-based modification logic and verification workflow.


## Overview

The `edit_file` tool is designed for high-precision, surgical modifications to files within the TaskVector framework. Instead of overwriting entire files, it utilizes a unified diff patch system to minimize token consumption and reduce the risk of accidental regressions.


## Components

### 1. Configuration (`tool.yaml`)
- **ID**: `edit_file`
- **Workflow**: Linked to `edit_file_workflow.json`
- **Purpose**: Provides the metadata necessary for the framework to route the action to the correct execution logic.

### 2. Prompting Logic (`prompt.py`)
- **Mechanism**: Instructs the AI to generate edits using the unified diff format (`@@ -L,C +L,C @@`).
- **Benefit**: This ensures that only the changed lines are transmitted and applied, maintaining the integrity of the surrounding code.

### 3. Verification Loop (`follow_ups.py`)
- **Safety Constraint**: The tool implements a mandatory verification step. The agent is explicitly prompted: *'IMPORTANT: You requested a file edit. You must check the result.'*
- **Workflow**: This enforces a 'Write-Verify-Summarize' cycle, ensuring the patch was applied as intended before the agent proceeds.


## Technical Summary Table

| Component | Purpose | Key Detail |
| :--- | :--- | :--- |
| `tool.yaml` | Metadata | Links tool ID to workflow |
| `prompt.py` | Instruction | Defines unified diff format |
| `follow_ups.py` | Validation | Forces agent to verify edit result |
