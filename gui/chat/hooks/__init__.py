"""UI hooks"""

from .on_apply import on_apply_hook

__all__ = [
    "on_apply_hook",  # use this hook to apdate workflow graph after the agent turn
]
