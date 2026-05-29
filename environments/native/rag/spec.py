"""
RagEnvironmentSpec: RAG unit workflows (search, index, embed, Chroma) plus common data_bi helpers used in ingest graphs.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from core.schemas.process_graph import ProcessGraph
from core.schemas.training_config import GoalConfig
from units.data_bi import register_data_bi_units
from units.rag import register_rag_units


class RagEnvironmentSpec:
    """EnvironmentSpec for RAG-tagged units; also registers data_bi (Filter, JsonParser, …) for typical RAG pipelines."""

    def __init__(self, **kwargs: Any):
        self._kwargs = kwargs

    def register_units(self) -> None:
        register_rag_units()
        try:
            register_data_bi_units()
        except Exception:
            pass

    def build_initial_state(
        self,
        process_graph: ProcessGraph,
        goal: GoalConfig,
        options: dict[str, Any] | None,
        randomize: bool,
        np_random: np.random.Generator,
        **kwargs: Any,
    ) -> dict[str, Any]:
        return {}

    def check_done(
        self,
        outputs: dict[str, Any],
        goal_override: dict[str, Any],
        step_count: int,
        max_steps: int,
        **kwargs: Any,
    ) -> tuple[bool, bool]:
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
