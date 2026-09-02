from __future__ import annotations

from pydantic import BaseModel

from core.schemas.primitives import JsonValue, WorkflowInputs
from core.schemas.process_graph import ProcessGraph


class WorkflowDesignerWorkflowInputs(BaseModel):
    """Typed inputs injected into the workflow designer workflow."""

    inject_user_message: str
    inject_graph: ProcessGraph
    inject_turn_state: str
    inject_recent_changes_block: str = ""
    inject_last_edit_block: str = ""
    inject_follow_up_context: str = ""
    inject_previous_turn: str = ""
    inject_session_language: str = ""

    inject_add_environment_edit: str = ""
    inject_add_code_block_edit: str = ""
    inject_run_workflow: str = ""
    inject_ai_training_integration: str = ""
    inject_running_flow_line: str = ""
    inject_debugging_line: str = ""
    inject_coding_line: str = ""

    inject_list_unit_edit: str = ""
    inject_list_environment_edit: str = ""

    def to_workflow_inputs(self) -> WorkflowInputs:
        """Serialize the typed inputs to the workflow engine's input format."""

        graph_data: JsonValue = self.inject_graph.model_dump(
            mode="json",
            by_alias=True,
        )

        def data(value: JsonValue) -> dict[str, JsonValue]:
            return {"data": value}

        return {
            "inject_user_message": data(self.inject_user_message),
            "inject_graph": data(graph_data),
            "inject_turn_state": data(self.inject_turn_state),
            "inject_recent_changes_block": data(
                self.inject_recent_changes_block
            ),
            "inject_last_edit_block": data(self.inject_last_edit_block),
            "inject_follow_up_context": data(self.inject_follow_up_context),
            "inject_previous_turn": data(self.inject_previous_turn),
            "inject_session_language": data(self.inject_session_language),
            "inject_add_environment_edit": data(
                self.inject_add_environment_edit
            ),
            "inject_add_code_block_edit": data(
                self.inject_add_code_block_edit
            ),
            "inject_run_workflow": data(self.inject_run_workflow),
            "inject_ai_training_integration": data(
                self.inject_ai_training_integration
            ),
            "inject_running_flow_line": data(
                self.inject_running_flow_line
            ),
            "inject_debugging_line": data(self.inject_debugging_line),
            "inject_coding_line": data(self.inject_coding_line),
            "inject_list_unit_edit": data(self.inject_list_unit_edit),
            "inject_list_environment_edit": data(
                self.inject_list_environment_edit
            ),
        }
