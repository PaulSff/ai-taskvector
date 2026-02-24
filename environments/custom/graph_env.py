"""
Graph-based environment: thin gym.Env around GraphExecutor.

Observation/action spaces and reward logic come from training config and process graph
(RLAgent wiring). All simulation logic lives in the unit registry.
"""
from __future__ import annotations

from typing import Any

import gymnasium as gym
import numpy as np

from graph_executor.executor import GraphExecutor
from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig, RewardsConfig
from units.agent import register_agent_units
from units.oracle import register_oracle_units
from units.thermodynamic import register_thermodynamic_units

# Ensure all units are registered (thermodynamic + agent + oracle)
register_thermodynamic_units()
register_agent_units()
register_oracle_units()


def _action_to_setpoints(action: np.ndarray) -> list[float]:
    """Map [-1, 1] action to [0, 1] valve setpoints."""
    return [float((x + 1) / 2) for x in np.clip(action, -1.0, 1.0)]


class GraphEnv(gym.Env):
    """
    Gymnasium env that runs the process graph via GraphExecutor.

    Observation: sensor outputs (from get_agent_observation_input_ids)
    Action: valve setpoints (to get_agent_action_output_ids), mapped from [-1,1] to [0,1]
    """

    metadata = {"render_modes": ["human"], "render_fps": 4}

    def __init__(
        self,
        process_graph: ProcessGraph,
        goal: GoalConfig,
        *,
        dt: float = 0.1,
        max_steps: int = 600,
        initial_temp: float = 20.0,
        initial_volume_ratio: float | None = None,
        rewards_config: RewardsConfig | None = None,
        render_mode: str | None = None,
        randomize_params: bool = False,
    ):
        super().__init__()
        self.process_graph = process_graph
        self.goal = goal
        self.dt = dt
        self.max_steps = max_steps
        self.initial_temp = initial_temp
        self.initial_volume_ratio = initial_volume_ratio
        self.rewards_config = rewards_config
        self.render_mode = render_mode
        self.randomize_params = randomize_params

        self.executor = GraphExecutor(process_graph)
        n_obs = max(len(self.executor._obs_ids), 1)
        n_act = max(len(self.executor._action_ids), 1)

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

    def reset(
        self,
        seed: int | None = None,
        options: dict[str, Any] | None = None,
    ) -> tuple[np.ndarray, dict]:
        super().reset(seed=seed)
        target = self.goal.target_temp
        if options and "target_temp" in options:
            target = float(options["target_temp"])
        if self.randomize_params and (options is None or not options.get("randomize") == False):
            if options and "target_temp" in options:
                pass
            else:
                target = float(self.np_random.uniform(30.0, 45.0))
        self._target_temp = target

        tank_id = next((u.id for u in self.process_graph.units if u.type == "Tank"), None)
        capacity = 1.0
        if tank_id:
            u = next((x for x in self.process_graph.units if x.id == tank_id), None)
            if u and u.params:
                capacity = float(u.params.get("capacity", 1.0))
        vol_ratio = self.initial_volume_ratio
        if vol_ratio is None and options and "initial_volume" in options:
            vol_ratio = float(options["initial_volume"])
        if vol_ratio is None and self.randomize_params:
            vol_ratio = float(self.np_random.uniform(0.0, 0.95))
        if vol_ratio is None:
            vol_ratio = 0.5
        vol_ratio = float(np.clip(vol_ratio, 0.01, 0.99))
        initial_state = {}
        if tank_id:
            initial_state[tank_id] = {
                "volume": capacity * vol_ratio,
                "temp": self.initial_temp,
                "hot_temp": 60.0,
                "cold_temp": 10.0,
            }
        obs, info = self.executor.reset(initial_state=initial_state)
        self.step_count = 0
        outputs = info.get("outputs", {})
        if tank_id and tank_id in outputs:
            t = outputs[tank_id]
            info["temperature"] = t.get("temp", self.initial_temp)
            info["volume"] = t.get("volume", capacity * vol_ratio)
            info["volume_ratio"] = t.get("volume_ratio", vol_ratio)
        else:
            info["temperature"] = self.initial_temp
            info["volume"] = capacity * vol_ratio
            info["volume_ratio"] = vol_ratio
        info["target_temp"] = self._target_temp
        return np.array(obs, dtype=np.float32), info

    def step(
        self,
        action: np.ndarray | list[float],
    ) -> tuple[np.ndarray, float, bool, bool, dict]:
        setpoints = _action_to_setpoints(np.asarray(action))
        obs, info = self.executor.step(self.dt, setpoints)
        self.step_count += 1

        outputs = info.get("outputs", {})
        tank_id = next((u.id for u in self.process_graph.units if u.type == "Tank"), None)
        t = outputs.get(tank_id, {}) if tank_id else {}
        temp = t.get("temp", 0.0)
        volume_ratio = t.get("volume_ratio", 0.0)
        target_vol = self.goal.target_volume_ratio
        vol_lo, vol_hi = (target_vol[0], target_vol[1]) if target_vol else (0.8, 0.85)

        temp_error = abs(temp - self._target_temp)
        reward = -temp_error

        if volume_ratio >= vol_lo and volume_ratio <= vol_hi:
            reward += 10.0
        elif volume_ratio >= 0.75:
            reward += 5.0
        elif volume_ratio >= 0.70:
            reward += 2.0

        if temp_error < 0.5:
            reward += 10.0
        elif temp_error < 1.0:
            reward += 5.0
        if temp_error < 0.1 and vol_lo <= volume_ratio <= vol_hi:
            reward += 20.0

        # Penalties (simplified)
        reward -= 0.01 * sum(setpoints[:3])  # flow penalty
        reward -= 0.1 * (setpoints[2] if len(setpoints) > 2 else 0)  # dump penalty

        if self.rewards_config and getattr(self.rewards_config, "rules", None):
            from environments.reward_rules import evaluate_rules
            state_dict = {
                "temp_error": float(temp_error),
                "volume": info.get("volume", 0.0),
                "volume_ratio": float(volume_ratio),
                "current_temp": float(temp),
                "target_temp": float(self._target_temp),
                "step_count": self.step_count,
            }
            reward += evaluate_rules(state_dict, self.rewards_config.rules)

        terminated = temp_error < 0.1 and vol_lo <= volume_ratio <= vol_hi
        truncated = self.step_count >= self.max_steps

        info["temperature"] = temp
        info["volume"] = t.get("volume", 0.0)
        info["temp_error"] = temp_error
        info["volume_ratio"] = volume_ratio
        info["target_temp"] = self._target_temp

        return (
            np.array(obs, dtype=np.float32),
            float(reward),
            bool(terminated),
            bool(truncated),
            info,
        )

    def render(self) -> None:
        if self.render_mode == "human":
            info = getattr(self.executor, "_outputs", {})
            tank_id = next((u.id for u in self.process_graph.units if u.type == "Tank"), None)
            t = info.get(tank_id, {}) if tank_id else {}
            temp = t.get("temp", 0)
            vol = t.get("volume_ratio", 0) * 100
            print(
                f"Step: {self.step_count}, Temp: {temp:.2f}°C (target: {getattr(self, '_target_temp', 0):.1f}°C), "
                f"Vol: {vol:.1f}%"
            )
