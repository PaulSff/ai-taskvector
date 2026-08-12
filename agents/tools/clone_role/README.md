# Clone Role Tool

A TaskVector tool that allows for the rapid creation of new AI roles by cloning existing role templates and customizing their behavior, responsibilities, and toolsets.


## Overview

The `clone_role` tool simplifies the process of expanding the AI agent ecosystem within TaskVector. Instead of creating role definitions from scratch, it leverages an existing role as a blueprint and overrides key attributes to define a new persona.


## Action Schema

The tool is invoked via a JSON action with the following parameters:
- `new_role_name`: The unique identifier for the new role (lowercase).
- `character_name`: The display name of the agent (e.g., 'Alex').
- `responsibility`: A high-level description of the role's purpose.
- `intro_brief`: A one-sentence introduction.
- `prompt_duties`: Detailed instructions on what the agent should do.
- `prompt_conversational_behavior`: Guidelines on how the agent should interact.
- `prompt_reasoning`: Logic and step-by-step thinking requirements.
- `tools`: A list of available tools the new role can access.


## Workflow Architecture

The tool implements a native TaskVector workflow (`clone_role_workflow.json`) consisting of:
1. **Inject Unit**: Captures the action parameters from the agent.
2. **CloneRole Unit**: Executes the backend logic to duplicate the role package and write the new configuration files.


## File Structure

- `tool.yaml`: Tool configuration and workflow mapping.
- `prompt.py`: Action definition for the LLM.
- `follow_ups.py`: Post-execution verification prompts.
- `clone_role_workflow.json`: The operational graph.
