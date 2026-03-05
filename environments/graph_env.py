"""
Generic graph-based environment: thin gym.Env around GraphExecutor.

Environment-agnostic orchestration. All process-type-specific logic lives in
EnvSpec (build_initial_state, check_done, extend_info, compat attrs).
Canonical units and RLAgent/LLMAgent/RLGym/RLOracle are environment-agnostic
and registered for every graph env regardless of spec.
"""
from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np

from graph_executor.executor import GraphExecutor
from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig, RewardsConfig

from environments.spec import EnvSpec
from units.register_env_agnostic import register_env_agnostic_units


def _action_to_setpoints(action: np.ndarray) -> list[float]:
    """Map [-1, 1] action to [0, 1] valve setpoints."""
    return [float((x + 1) / 2) for x in np.clip(action, -1.0, 1.0)]


class GraphEnv(gym.Env):
    """
    Generic gym.Env that runs the process graph via GraphExecutor.

    Delegates to EnvSpec for: initial state, done condition, info extension,
    compatibility attributes, render.
    """

    metadata = {"render_modes": ["human"], "render_fps": 4}

    def __init__(
        self,
        process_graph: ProcessGraph,
        goal: GoalConfig,
        spec: EnvSpec,
        *,
        dt: float = 0.1,
        max_steps: int = 600,
        rewards_config: RewardsConfig | None = None,
        render_mode: str | None = None,
        randomize_params: bool = False,
        **kwargs: Any,
    ):
        super().__init__()
        self.process_graph = process_graph
        self.goal = goal
        self.spec = spec
        self.dt = dt
        self.max_steps = max_steps
        self.rewards_config = rewards_config
        self.render_mode = render_mode
        self.randomize_params = randomize_params
        self._kwargs = kwargs

        spec.register_units()
        register_env_agnostic_units()  # canonical + RLAgent/LLMAgent/RLGym/RLOracle for all envs
        self.executor = GraphExecutor(process_graph)
        n_obs = getattr(self.executor, "_n_obs", None) or max(len(self.executor._obs_ids), 1)
        n_act = getattr(self.executor, "_n_act", None) or max(len(self.executor._action_ids), 1)

        self.observation_space = gym.spaces.Box(
            low=np.zeros(n_obs, dtype=np.float32),
            high=np.ones(n_obs, dtype=np.float32),
            dtype=np.float32,
        )
        self.action_space = gym.spaces.Box(
            low=np.full(n_act, -1.0, dtype=np.float32),
            high=np.ones(n_act, dtype=np.float32),
            dtype=np.float32,
        )
        self.step_count: int = 0

        if hasattr(spec, "manual_step"):
            self.manual_step = lambda *a, **k: spec.manual_step(self, *a, **k)

    def __getattr__(self, name: str) -> Any:
        """Delegate compatibility attrs to spec."""
        try:
            return self.spec.get_compat_attr(self, name)
        except AttributeError:
            raise AttributeError(f"'{type(self).__name__}' object has no attribute '{name}'")

    def reset(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        initial_state = self.spec.build_initial_state(
            self.process_graph,
            self.goal,
            options,
            self.randomize_params,
            self.np_random,
            **self._kwargs,
        )
        obs, info = self.executor.reset(initial_state=initial_state)
        self.step_count = 0
        self.spec.extend_info(
            info,
            info.get("outputs", {}),
            initial_state,
            process_graph=self.process_graph,
            **self._kwargs,
        )
        return np.array(obs, dtype=np.float32), info

    def step(
        self,
        action: np.ndarray | list[float],
    ) -> tuple[np.ndarray, float, bool, bool, dict]:
        setpoints = _action_to_setpoints(np.asarray(action))
        obs, info = self.executor.step(self.dt, setpoints)
        self.step_count += 1

        outputs = info.get("outputs", {})
        goal_override = self.spec.get_goal_override(self, **self._kwargs)

        # Use reward/done from canonical StepRewards when present (same as external path)
        if "reward" in info and "done" in info:
            reward = float(info["reward"])
            done_flag = bool(info["done"])
            terminated = done_flag
            truncated = False
        else:
            from rewards import evaluate_reward
            reward = evaluate_reward(
                self.rewards_config,
                outputs,
                goal_override,
                list(obs),
                self.step_count,
                self.max_steps,
                action=list(setpoints),
            )
            terminated, truncated = self.spec.check_done(
                outputs,
                goal_override,
                self.step_count,
                self.max_steps,
                **{**self._kwargs, "process_graph": self.process_graph},
            )

        self.spec.extend_info(
            info,
            outputs,
            None,
            process_graph=self.process_graph,
            **self._kwargs,
        )

        return (
            np.array(obs, dtype=np.float32),
            float(reward),
            bool(terminated),
            bool(truncated),
            info,
        )

    def render(self) -> None:
        if self.render_mode == "human" and hasattr(self.spec, "render"):
            self.spec.render(self)
