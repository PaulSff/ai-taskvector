from __future__ import annotations

from dataclasses import dataclass, field

from schemas.process_graph import ProcessGraph


def _snapshot(graph: ProcessGraph | None) -> dict | None:
    """Serialize graph to a JSON-friendly dict (aliases preserved)."""
    if graph is None:
        return None
    # by_alias preserves Connection aliases: "from"/"to"
    return graph.model_dump(by_alias=True)


def _restore(snapshot: dict | None) -> ProcessGraph | None:
    """Restore graph from snapshot dict."""
    if snapshot is None:
        return None
    return ProcessGraph.model_validate(snapshot)


@dataclass
class UndoRedoManager:
    """
    Simple snapshot-based undo/redo for ProcessGraph.

    Stores snapshots as plain dicts (or None for "no graph loaded") so there are no
    shared references between history and the live graph.
    """

    max_depth: int = 50
    _undo: list[dict | None] = field(default_factory=list)
    _redo: list[dict | None] = field(default_factory=list)

    def clear(self) -> None:
        self._undo.clear()
        self._redo.clear()

    def can_undo(self) -> bool:
        return len(self._undo) > 0

    def can_redo(self) -> bool:
        return len(self._redo) > 0

    def get_previous_snapshot(self) -> dict | None:
        """Return the top of the undo stack (state before last change), or None if empty."""
        if not self._undo:
            return None
        return self._undo[-1]

    def push_undo(self, current: ProcessGraph | None) -> None:
        """Record current state to undo stack and clear redo stack."""
        self._undo.append(_snapshot(current))
        if len(self._undo) > self.max_depth:
            self._undo = self._undo[-self.max_depth :]
        self._redo.clear()

    def undo(self, current: ProcessGraph | None) -> ProcessGraph | None:
        """Undo to previous snapshot. Raises IndexError if nothing to undo."""
        snap = self._undo.pop()
        self._redo.append(_snapshot(current))
        if len(self._redo) > self.max_depth:
            self._redo = self._redo[-self.max_depth :]
        return _restore(snap)

    def redo(self, current: ProcessGraph | None) -> ProcessGraph | None:
        """Redo to next snapshot. Raises IndexError if nothing to redo."""
        snap = self._redo.pop()
        self._undo.append(_snapshot(current))
        if len(self._undo) > self.max_depth:
            self._undo = self._undo[-self.max_depth :]
        return _restore(snap)

