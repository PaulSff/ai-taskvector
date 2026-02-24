"""
EnvSpec: tiny integration layer for custom graph-based environments.

Each custom env type (thermodynamic, chemical, etc.) provides a spec that tells
the generic GraphEnv how to build initial state, check done, extend info, and
optionally provide compatibility attributes (e.g. current_temp for water_tank_simulator).
"""
from __future__ import annotations

from typing import Any, Protocol

import numpy as np

from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig


class EnvSpec(Protocol):
    """Tiny integration layer per custom env type."""

    def register_units(self) -> None:
        """Register units the graph needs (Source, Valve, Tank, etc.)."""

    def build_initial_state(
        self,
        process_graph: ProcessGraph,
        goal: GoalConfig,
        options: dict[str, Any] | None,
        randomize: bool,
        np_random: np.random.Generator,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """Build unit_id -> state dict for executor.reset(initial_state=...)."""

    def check_done(
        self,
        outputs: dict[str, Any],
        goal_override: dict[str, Any],
        step_count: int,
        max_steps: int,
        **kwargs: Any,
    ) -> tuple[bool, bool]:
        """Return (terminated, truncated)."""

    def extend_info(
        self,
        info: dict[str, Any],
        outputs: dict[str, Any],
        initial_state: dict[str, Any] | None,
        **kwargs: Any,
    ) -> None:
        """Add spec-specific keys to info (mutates info in place)."""

    def get_goal_override(self, env: Any, **kwargs: Any) -> dict[str, Any]:
        """Return goal dict for evaluate_reward (e.g. target_temp, target_volume_ratio)."""

    def get_compat_attr(self, env: Any, name: str) -> Any:
        """Return value for compatibility attr (current_temp, hot_flow, etc.) or raise AttributeError."""
