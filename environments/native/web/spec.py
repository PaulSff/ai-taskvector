"""
WebEnvSpec: integration layer for web workflows (browser, web_search units).
Python-only; no export to Node-RED/PyFlow. Used when environment_type=web.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig

from units.web import register_web_units


class WebEnvSpec:
    """EnvSpec for web workflows (fetch URL, search). Step-based; no physical state."""

    def register_units(self) -> None:
        register_web_units()

    def build_initial_state(
        self,
        process_graph: ProcessGraph,
        goal: GoalConfig,
        options: dict[str, Any] | None,
        randomize: bool,
        np_random: np.random.Generator,
        **kwargs: Any,
    ) -> dict[str, Any]:
        """No initial state required for web units."""
        return {}

    def check_done(
        self,
        outputs: dict[str, Any],
        goal_override: dict[str, Any],
        step_count: int,
        max_steps: int,
        **kwargs: Any,
    ) -> tuple[bool, bool]:
        """Truncate at max_steps."""
        return False, step_count >= max_steps

    def extend_info(
        self,
        info: dict[str, Any],
        outputs: dict[str, Any],
        initial_state: dict[str, Any] | None,
        **kwargs: Any,
    ) -> None:
        pass

    def get_goal_override(self, env: Any, **kwargs: Any) -> dict[str, Any]:
        return {}

    def get_compat_attr(self, env: Any, name: str) -> Any:
        raise AttributeError(name)
