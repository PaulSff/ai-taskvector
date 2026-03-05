"""
ThermodynamicEnvSpec: integration layer for temperature-mixing process.
"""
from __future__ import annotations

from typing import Any

import numpy as np

from schemas.process_graph import ProcessGraph
from schemas.training_config import GoalConfig

from units.thermodynamic import register_thermodynamic_units


class ThermodynamicEnvSpec:
    """EnvSpec for thermodynamic (temperature mixing) process."""

    def __init__(self, **kwargs: Any):
        self._kwargs = kwargs
        self._target_temp: float = 0.0  # set in build_initial_state

    def register_units(self) -> None:
        register_thermodynamic_units()
        # Canonical + RLAgent/LLMAgent/RLGym/RLOracle are env-agnostic (registered in GraphEnv)

    def build_initial_state(
        self,
        process_graph: ProcessGraph,
        goal: GoalConfig,
        options: dict[str, Any] | None,
        randomize: bool,
        np_random: np.random.Generator,
        **kwargs: Any,
    ) -> dict[str, Any]:
        kw = {**self._kwargs, **kwargs}
        initial_temp = float(kw.get("initial_temp", 20.0))
        initial_volume_ratio = kw.get("initial_volume_ratio")

        # Target temp
        target = goal.target_temp
        if options and "target_temp" in options:
            target = float(options["target_temp"])
        if randomize and (options is None or options.get("randomize") != False):
            if not (options and "target_temp" in options):
                target = float(np_random.uniform(30.0, 45.0))
        self._target_temp = float(target or 37.0)

        tank_id = next((u.id for u in process_graph.units if u.type == "Tank"), None)
        capacity = 1.0
        if tank_id:
            u = next((x for x in process_graph.units if x.id == tank_id), None)
            if u and u.params:
                capacity = float(u.params.get("capacity", 1.0))

        vol_ratio = initial_volume_ratio
        if vol_ratio is None and options and "initial_volume" in options:
            vol_ratio = float(options["initial_volume"])
        if vol_ratio is None and randomize:
            vol_ratio = float(np_random.uniform(0.0, 0.95))
        if vol_ratio is None:
            vol_ratio = 0.5
        vol_ratio = float(np.clip(vol_ratio, 0.01, 0.99))

        initial_state: dict[str, Any] = {}
        if tank_id:
            initial_state[tank_id] = {
                "volume": capacity * vol_ratio,
                "temp": initial_temp,
                "hot_temp": 60.0,
                "cold_temp": 10.0,
            }
        return initial_state

    def check_done(
        self,
        outputs: dict[str, Any],
        goal_override: dict[str, Any],
        step_count: int,
        max_steps: int,
        **kwargs: Any,
    ) -> tuple[bool, bool]:
        process_graph: ProcessGraph | None = kwargs.get("process_graph")
        tank_id = next((u.id for u in process_graph.units if u.type == "Tank"), None) if process_graph else None
        t = outputs.get(tank_id, {}) if tank_id else {}
        temp = t.get("temp", 0.0)
        volume_ratio = t.get("volume_ratio", 0.0)
        target_vol = goal_override.get("target_volume_ratio")
        vol_lo, vol_hi = (target_vol[0], target_vol[1]) if target_vol else (0.8, 0.85)

        temp_error = abs(temp - self._target_temp)
        terminated = temp_error < 0.1 and vol_lo <= volume_ratio <= vol_hi
        truncated = step_count >= max_steps
        return terminated, truncated

    def extend_info(
        self,
        info: dict[str, Any],
        outputs: dict[str, Any],
        initial_state: dict[str, Any] | None,
        **kwargs: Any,
    ) -> None:
        process_graph: ProcessGraph | None = kwargs.get("process_graph")
        tank_id = next((u.id for u in process_graph.units if u.type == "Tank"), None) if process_graph else None
        capacity = 1.0
        if tank_id and process_graph:
            u = next((x for x in process_graph.units if x.id == tank_id), None)
            if u and u.params:
                capacity = float(u.params.get("capacity", 1.0))
        t = outputs.get(tank_id, {}) if tank_id else {}
        temp = t.get("temp", 0.0)
        volume = t.get("volume", 0.0)
        volume_ratio = t.get("volume_ratio", 0.5)

        info["temperature"] = temp
        info["volume"] = volume
        info["volume_ratio"] = volume_ratio
        info["target_temp"] = self._target_temp
        info["temp_error"] = abs(temp - self._target_temp)

    def get_goal_override(self, env: Any, **kwargs: Any) -> dict[str, Any]:
        out: dict[str, Any] = {"target_temp": self._target_temp}
        if env.goal.target_volume_ratio:
            out["target_volume_ratio"] = list(env.goal.target_volume_ratio)
        return out

    def get_compat_attr(self, env: Any, name: str) -> Any:
        pg = env.process_graph
        ex = env.executor
        outputs = getattr(ex, "_outputs", {})

        if name == "current_temp":
            tank_id = next((u.id for u in pg.units if u.type == "Tank"), None)
            if tank_id:
                t = outputs.get(tank_id, {})
                return float(t.get("temp", 20.0))
            return 20.0
        if name == "target_temp":
            return self._target_temp
        if name == "volume":
            tank_id = next((u.id for u in pg.units if u.type == "Tank"), None)
            if tank_id:
                return float(outputs.get(tank_id, {}).get("volume", 0.0))
            return 0.0
        if name == "tank_capacity":
            tank_id = next((u.id for u in pg.units if u.type == "Tank"), None)
            if tank_id:
                u = next((x for x in pg.units if x.id == tank_id), None)
                if u and u.params:
                    return float(u.params.get("capacity", 1.0))
            return 1.0
        if name == "hot_flow":
            hot_valve = next((u.id for u in pg.units if u.type == "Valve" and "hot" in u.id.lower()), None)
            if hot_valve and hot_valve in outputs:
                return float(outputs[hot_valve].get("flow", 0.0))
            return 0.0
        if name == "cold_flow":
            cold_valve = next((u.id for u in pg.units if u.type == "Valve" and "cold" in u.id.lower()), None)
            if cold_valve and cold_valve in outputs:
                return float(outputs[cold_valve].get("flow", 0.0))
            return 0.0
        if name == "max_flow_rate":
            hot = next((u for u in pg.units if u.type == "Source" and u.params.get("temp", 0) >= 50), None)
            if hot and hot.params:
                return float(hot.params.get("max_flow", 1.0))
            return 1.0
        raise AttributeError(name)

    def manual_step(
        self,
        env: Any,
        hot_flow: float | None = None,
        cold_flow: float | None = None,
        dump_flow: float | None = None,
        *,
        disable_drift: bool = True,
    ) -> tuple:
        """Manual step with direct flow rates (for water_tank_simulator)."""
        max_flow = self.get_compat_attr(env, "max_flow_rate")
        h = (hot_flow if hot_flow is not None else self.get_compat_attr(env, "hot_flow")) / max(max_flow, 1e-6)
        c = (cold_flow if cold_flow is not None else self.get_compat_attr(env, "cold_flow")) / max(max_flow, 1e-6)
        d = (dump_flow if dump_flow is not None else 0.0) / max(max_flow, 1e-6)
        action = np.array([h * 2 - 1, c * 2 - 1, d * 2 - 1], dtype=np.float32)
        return env.step(action)

    def render(self, env: Any) -> None:
        outputs = getattr(env.executor, "_outputs", {})
        tank_id = next((u.id for u in env.process_graph.units if u.type == "Tank"), None)
        t = outputs.get(tank_id, {}) if tank_id else {}
        temp = t.get("temp", 0)
        vol = t.get("volume_ratio", 0) * 100
        print(
            f"Step: {env.step_count}, Temp: {temp:.2f}°C (target: {self._target_temp:.1f}°C), "
            f"Vol: {vol:.1f}%"
        )