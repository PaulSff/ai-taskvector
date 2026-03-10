"""Graph edit units: Inject + one unit per edit action. Canonical (native runtime only)."""

from units.canonical.inject import register_graph_inject
from units.canonical.graph_edit.add_unit import register_add_unit
from units.canonical.graph_edit.add_pipeline import register_add_pipeline
from units.canonical.graph_edit.remove_unit import register_remove_unit
from units.canonical.graph_edit.connect import register_connect
from units.canonical.graph_edit.disconnect import register_disconnect
from units.canonical.graph_edit.replace_unit import register_replace_unit
from units.canonical.graph_edit.replace_graph import register_replace_graph
from units.canonical.graph_edit.add_code_block import register_add_code_block
from units.canonical.graph_edit.add_comment import register_add_comment
from units.canonical.graph_edit.add_environment import register_add_environment
from units.canonical.graph_edit.no_edit import register_no_edit
from units.canonical.graph_edit.todo_list import register_todo_list


def register_graph_edit_flow_units() -> None:
    """Register Inject and all edit units (add_unit, connect, disconnect, etc.)."""
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
