"""Graph edit units: graph_inject + one unit per edit action. Env-agnostic; used by assistant edit workflows."""

from units.env_agnostic.graph_edit.inject import register_graph_inject
from units.env_agnostic.graph_edit.add_unit import register_add_unit
from units.env_agnostic.graph_edit.add_pipeline import register_add_pipeline
from units.env_agnostic.graph_edit.remove_unit import register_remove_unit
from units.env_agnostic.graph_edit.connect import register_connect
from units.env_agnostic.graph_edit.disconnect import register_disconnect
from units.env_agnostic.graph_edit.replace_unit import register_replace_unit
from units.env_agnostic.graph_edit.replace_graph import register_replace_graph
from units.env_agnostic.graph_edit.add_code_block import register_add_code_block
from units.env_agnostic.graph_edit.add_comment import register_add_comment
from units.env_agnostic.graph_edit.add_environment import register_add_environment
from units.env_agnostic.graph_edit.no_edit import register_no_edit
from units.env_agnostic.graph_edit.todo_list import register_todo_list


def register_graph_edit_flow_units() -> None:
    """Register graph_inject and all edit units (add_unit, connect, disconnect, etc.)."""
    register_graph_inject()
    register_add_unit()
    register_add_pipeline()
    register_remove_unit()
    register_connect()
    register_disconnect()
    register_replace_unit()
    register_replace_graph()
    register_add_code_block()
    register_add_comment()
    register_add_environment()
    register_no_edit()
    register_todo_list()


__all__ = ["register_graph_edit_flow_units"]
