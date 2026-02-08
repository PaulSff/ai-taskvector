"""Process-graph dialogs (add/remove node/link, view code)."""

from gui.flet.dialogs.dialog_add_link import open_add_link_dialog
from gui.flet.dialogs.dialog_add_node import open_add_node_dialog
from gui.flet.dialogs.dialog_common import dict_to_graph, graph_to_dict
from gui.flet.dialogs.dialog_remove_link import open_remove_link_dialog
from gui.flet.dialogs.dialog_view_graph_code import open_view_graph_code_dialog

__all__ = [
    "dict_to_graph",
    "graph_to_dict",
    "open_add_link_dialog",
    "open_add_node_dialog",
    "open_remove_link_dialog",
    "open_view_graph_code_dialog",
]
