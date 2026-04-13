"""Re-export ``ProcessGraph`` for GUI code that must not import ``core.schemas`` directly."""

from core.schemas.process_graph import ProcessGraph

__all__ = ["ProcessGraph"]
