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
        self._target_temp: float = float(goal.target_temp or 37.0)  # updated in reset

    @property
    def current_temp(self) -> float:
        """Current tank temperature (for compatibility with TemperatureControlEnv API)."""
        tank_id = next((u.id for u in self.process_graph.units if u.type == "Tank"), None)
        if tank_id:
            t = getattr(self.executor, "_outputs", {}).get(tank_id, {})
            return float(t.get("temp", self.initial_temp))
        return self.initial_temp

    @property
    def target_temp(self) -> float:
        """Target temperature (for compatibility with TemperatureControlEnv API)."""
        return getattr(self, "_target_temp", self.goal.target_temp or 37.0)

    @property
    def volume(self) -> float:
        """Current tank volume (for compatibility with water_tank_simulator)."""
        tank_id = next((u.id for u in self.process_graph.units if u.type == "Tank"), None)
        if tank_id:
            t = getattr(self.executor, "_outputs", {}).get(tank_id, {})
            return float(t.get("volume", 0.0))
        return 0.0

    @property
    def tank_capacity(self) -> float:
        """Tank capacity (for compatibility with water_tank_simulator)."""
        tank_id = next((u.id for u in self.process_graph.units if u.type == "Tank"), None)
        if tank_id:
            u = next((x for x in self.process_graph.units if x.id == tank_id), None)
            if u and u.params:
                return float(u.params.get("capacity", 1.0))
        return 1.0

    @property
    def hot_flow(self) -> float:
        """Hot valve flow (for compatibility with water_tank_simulator)."""
        outputs = getattr(self.executor, "_outputs", {})
        hot_valve = next((u.id for u in self.process_graph.units if u.type == "Valve" and "hot" in u.id.lower()), None)
        if hot_valve and hot_valve in outputs:
            return float(outputs[hot_valve].get("flow", 0.0))
        return 0.0

    @property
    def cold_flow(self) -> float:
        """Cold valve flow (for compatibility with water_tank_simulator)."""
        outputs = getattr(self.executor, "_outputs", {})
        cold_valve = next((u.id for u in self.process_graph.units if u.type == "Valve" and "cold" in u.id.lower()), None)
        if cold_valve and cold_valve in outputs:
            return float(outputs[cold_valve].get("flow", 0.0))
        return 0.0

    @property
    def max_flow_rate(self) -> float:
        """Max flow rate (for compatibility with water_tank_simulator)."""
        hot = next((u for u in self.process_graph.units if u.type == "Source" and u.params.get("temp", 0) >= 50), None)
        if hot and hot.params:
            return float(hot.params.get("max_flow", 1.0))
        return 1.0

    def manual_step(
        self,
        hot_flow: float | None = None,
        cold_flow: float | None = None,
        dump_flow: float | None = None,
        *,
        disable_drift: bool = True,
    ) -> tuple[np.ndarray, float, bool, bool, dict]:
        """Manual step with direct flow rates (for compatibility with water_tank_simulator)."""
        max_flow = self.max_flow_rate
        h = (hot_flow if hot_flow is not None else self.hot_flow) / max(max_flow, 1e-6)
        c = (cold_flow if cold_flow is not None else self.cold_flow) / max(max_flow, 1e-6)
        d = (dump_flow if dump_flow is not None else 0.0) / max(max_flow, 1e-6)
        # Map [0,1] to [-1,1] for action space
        action = np.array([h * 2 - 1, c * 2 - 1, d * 2 - 1], dtype=np.float32)
        return self.step(action)

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

        # Goal with runtime target_temp (for randomization)
        goal_override = {"target_temp": self._target_temp}
        if self.goal.target_volume_ratio:
            goal_override["target_volume_ratio"] = list(self.goal.target_volume_ratio)

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

        temp_error = abs(temp - self._target_temp)
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
