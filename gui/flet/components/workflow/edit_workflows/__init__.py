"""Edit workflows: one workflow per graph-edit action. Used by the GUI to apply single edits."""
from .runner import apply_edit_via_workflow

__all__ = ["apply_edit_via_workflow"]
