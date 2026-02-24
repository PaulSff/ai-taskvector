"""
Temperature Control Environment for Reinforcement Learning
Simulates mixing hot and cold water to reach a target temperature.
Optional RewardsConfig: formula and rules evaluated via rewards.evaluate_reward.
When process_graph is provided, observation and action spaces are derived from the RLAgent wiring.
"""
import gymnasium as gym
from gymnasium import spaces
import numpy as np

from schemas.process_graph import ProcessGraph
from schemas.training_config import RewardsConfig
from schemas.agent_node import get_agent_observation_input_ids, get_agent_action_output_ids


class TemperatureControlEnv(gym.Env):
    """
    Environment for controlling water temperature by mixing hot and cold water.
    
    State: [current_temperature, hot_flow_rate, cold_flow_rate, time_elapsed]
    Action: [hot_valve_adjustment, cold_valve_adjustment] (continuous, -1 to 1)
    """
    
    metadata = {"render_modes": ["human"], "render_fps": 4}
    
    def __init__(self,
                 target_temp=37.0,
                 initial_temp=20.0,
                 hot_water_temp=60.0,
                 cold_water_temp=10.0,
                 max_flow_rate=1.0,
                 max_dump_flow_rate=1.0,
                 mixed_water_cooling_rate=0.01,
                 dt=0.1,
                 max_steps=600,
                 render_mode=None,
                 randomize_params=False,
                 rewards_config: RewardsConfig | None = None,
                 process_graph: ProcessGraph | None = None):
        super().__init__()

        self.target_temp = target_temp
        self.initial_temp = initial_temp
        self.hot_water_temp = hot_water_temp
        self.cold_water_temp = cold_water_temp
        self.max_flow_rate = max_flow_rate
        self.max_dump_flow_rate = max_dump_flow_rate
        self.mixed_water_cooling_rate = mixed_water_cooling_rate
        self.dt = dt  # Time step in seconds
        self.max_steps = max_steps
        self.render_mode = render_mode
        self.randomize_params = randomize_params
        self.process_graph = process_graph

        # Observation/action wiring from process graph (RLAgent inputs/outputs)
        self._observation_input_ids = []
        self._action_output_ids = []
        if process_graph is not None:
            self._observation_input_ids = get_agent_observation_input_ids(process_graph)
            self._action_output_ids = get_agent_action_output_ids(process_graph)
        
        # Tank properties
        self.tank_capacity = 1.0  # normalized volume
        self.ambient_temp = 20.0
        self.temp_min = 0.0
        self.temp_max = 100.0
        
        # Supply instability parameters
        self.temp_drift_std = 0.2  # °C change per step
        self.flow_drift_std = 0.02  # 2% flow noise
        
        n_obs = len(self._observation_input_ids) if self._observation_input_ids else 7
        n_act = len(self._action_output_ids) if self._action_output_ids else 3
        # Observation: from graph (sensor → agent) or legacy 7-dim
        self.observation_space = spaces.Box(
            low=np.zeros(n_obs, dtype=np.float32),
            high=np.ones(n_obs, dtype=np.float32),
            dtype=np.float32
        )
        # Action: from graph (agent → valves) or legacy 3-dim
        self.action_space = spaces.Box(
            low=np.full(n_act, -1.0, dtype=np.float32),
            high=np.full(n_act, 1.0, dtype=np.float32),
            dtype=np.float32
        )
        
        # Internal state
        self.current_temp = None
        self.hot_flow = None
        self.cold_flow = None
        self.dump_flow = None
        self.volume = None
        self.hot_supply_temp = None
        self.cold_supply_temp = None
        self.step_count = None
        self.temperature_history = []
        self.disable_drift = False  # Flag to disable drift for manual control/testing
        self.rewards_config = rewards_config

    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        
        # Allow target_temp override via options (for testing specific targets)
        if options and 'target_temp' in options:
            self.target_temp = float(options['target_temp'])
        
        # Randomize physics within safe bounds if requested
        randomize = (options and options.get("randomize")) or self.randomize_params
        if randomize:
            # Only randomize target_temp if not explicitly set via options
            if not (options and 'target_temp' in options):
                self.target_temp = float(np.random.uniform(30.0, 45.0))
            self.initial_temp = float(np.random.uniform(15.0, 25.0))
            self.hot_water_temp = float(np.random.uniform(55.0, 90.0))
            self.cold_water_temp = float(np.random.uniform(0.0, 20.0))
            self.max_flow_rate = float(np.random.uniform(0.5, 1.5))
        
        # Set initial volume - allow override via options, otherwise randomize
        if options and 'initial_volume' in options:
            # Use specified initial volume (as ratio 0.0-1.0)
            initial_volume_ratio = float(np.clip(options['initial_volume'], 0.0, 1.0))
        else:
            # Always randomize initial volume from 0 to 0.95 of capacity
            # This makes the agent learn to handle different starting conditions
            initial_volume_ratio = np.random.uniform(0.0, 0.95)
        
        # Initialize state
        self.current_temp = np.clip(self.initial_temp, self.temp_min, self.temp_max)
        self.hot_flow = 0.0
        self.cold_flow = 0.0
        self.dump_flow = 0.0
        # Set initial volume (ensure minimum to avoid division issues)
        self.volume = max(self.tank_capacity * initial_volume_ratio, 0.01)
        
        # Debug: verify volume is set correctly (can be removed later)
        if options and 'initial_volume' in options:
            assert abs(self.volume - (self.tank_capacity * initial_volume_ratio)) < 0.001, \
                f"Volume mismatch: set {self.volume}, expected {self.tank_capacity * initial_volume_ratio}"
        self.hot_supply_temp = self.hot_water_temp
        self.cold_supply_temp = self.cold_water_temp
        self.step_count = 0
        self.temperature_history = [self.current_temp]
        
        observation = self._get_observation()
        info = {"temperature": self.current_temp}
        
        return observation, info
    
    def _apply_action_to_flows(self, action: np.ndarray) -> None:
        """Apply action vector to flows (order from graph: agent → valves)."""
        action = np.clip(action, self.action_space.low, self.action_space.high)
        change = 0.6
        if self._action_output_ids:
            for i, valve_id in enumerate(self._action_output_ids):
                if i >= len(action):
                    break
                delta = action[i] * change
                vid = valve_id.lower()
                if "hot" in vid and "valve" in vid:
                    self.hot_flow = np.clip(self.hot_flow + delta, 0.0, self.max_flow_rate)
                elif "cold" in vid and "valve" in vid:
                    self.cold_flow = np.clip(self.cold_flow + delta, 0.0, self.max_flow_rate)
                elif "dump" in vid and "valve" in vid:
                    self.dump_flow = np.clip(self.dump_flow + delta, 0.0, self.max_dump_flow_rate)
        else:
            self.hot_flow = np.clip(self.hot_flow + action[0] * change, 0.0, self.max_flow_rate)
            self.cold_flow = np.clip(self.cold_flow + action[1] * change, 0.0, self.max_flow_rate)
            self.dump_flow = np.clip(self.dump_flow + action[2] * change, 0.0, self.max_dump_flow_rate)

    def step(self, action):
        # Clip and apply action (from graph wiring or legacy [hot, cold, dump])
        self._apply_action_to_flows(action)
        
        # Introduce slow drift/instability in supplies (unless disabled)
        if not self.disable_drift:
            self.hot_supply_temp = np.clip(
                self.hot_supply_temp + np.random.normal(0.0, self.temp_drift_std),
                self.temp_min,
                self.temp_max
            )
            self.cold_supply_temp = np.clip(
                self.cold_supply_temp + np.random.normal(0.0, self.temp_drift_std),
                self.temp_min,
                self.temp_max
            )
        
        # Effective flows after supply noise (unless drift disabled)
        if not self.disable_drift:
            hot_flow_effective = np.clip(
                self.hot_flow * (1.0 + np.random.normal(0.0, self.flow_drift_std)),
                0.0,
                self.max_flow_rate
            )
            cold_flow_effective = np.clip(
                self.cold_flow * (1.0 + np.random.normal(0.0, self.flow_drift_std)),
                0.0,
                self.max_flow_rate
            )
            dump_flow_effective = np.clip(
                self.dump_flow * (1.0 + np.random.normal(0.0, self.flow_drift_std)),
                0.0,
                self.max_dump_flow_rate
            )
        else:
            hot_flow_effective = self.hot_flow
            cold_flow_effective = self.cold_flow
            dump_flow_effective = self.dump_flow
        
        total_inflow = hot_flow_effective + cold_flow_effective
        inflow_volume = total_inflow * self.dt
        dump_volume = dump_flow_effective * self.dt
        
        # Avoid complete empty tank
        previous_volume = max(self.volume, 1e-6)
        
        if total_inflow > 0.001:
            mixed_temp = (
                (hot_flow_effective * self.hot_supply_temp + 
                 cold_flow_effective * self.cold_supply_temp) / max(total_inflow, 1e-6)
            )
        else:
            mixed_temp = self.current_temp
        
        # Energy balance with dumping and inflow
        retained_energy = self.current_temp * max(previous_volume - dump_volume, 0.0)
        added_energy = mixed_temp * inflow_volume
        self.volume = np.clip(previous_volume - dump_volume + inflow_volume, 0.01, self.tank_capacity)
        self.current_temp = (retained_energy + added_energy) / self.volume
        
        # Natural cooling toward ambient
        self.current_temp = (
            self.current_temp - self.mixed_water_cooling_rate * (self.current_temp - self.ambient_temp)
        )
        self.current_temp = float(np.clip(self.current_temp, self.temp_min, self.temp_max))
        
        self.step_count += 1
        self.temperature_history.append(self.current_temp)

        volume_ratio = self.volume / self.tank_capacity
        outputs = self._build_outputs_for_reward(volume_ratio)
        goal = {"target_temp": self.target_temp, "target_volume_ratio": [0.8, 0.85]}
        observation = self._get_observation()

        from rewards import evaluate_reward
        reward = evaluate_reward(
            self.rewards_config,
            outputs,
            goal,
            list(observation),
            self.step_count,
            self.max_steps,
        )

        temp_error = abs(self.current_temp - self.target_temp)
        # Check if done - SUCCESS requires BOTH temperature AND volume in ideal range (80-85%)
        temp_success = temp_error < 0.1
        volume_success = volume_ratio >= 0.80 and volume_ratio <= 0.85  # Tank must be in ideal range (80-85%)
        terminated = temp_success and volume_success  # Success: correct temp AND volume in ideal range
        truncated = self.step_count >= self.max_steps  # Timeout

        observation = self._get_observation()
        info = {
            "temperature": self.current_temp,
            "temp_error": temp_error,
            "hot_flow": self.hot_flow,
            "cold_flow": self.cold_flow,
            "dump_flow": self.dump_flow,
            "volume": self.volume,
            "volume_ratio": volume_ratio,
            "hot_supply_temp": self.hot_supply_temp,
            "cold_supply_temp": self.cold_supply_temp,
        }
        
        return observation, reward, terminated, truncated, info
    
    def manual_step(self, hot_flow=None, cold_flow=None, dump_flow=None, 
                    hot_supply_temp=None, cold_supply_temp=None, disable_drift=True):
        """
        Manual step function that allows direct control of flows and supply temps.
        Useful for manual testing without going through the action system.
        
        Args:
            hot_flow: Direct hot water flow rate (None to keep current)
            cold_flow: Direct cold water flow rate (None to keep current)
            dump_flow: Direct dump flow rate (None to keep current)
            hot_supply_temp: Hot water supply temperature (None to keep current)
            cold_supply_temp: Cold water supply temperature (None to keep current)
            disable_drift: If True, disable random drift in supply temps/flows
        """
        # Update flows if provided
        if hot_flow is not None:
            self.hot_flow = np.clip(hot_flow, 0.0, self.max_flow_rate)
        if cold_flow is not None:
            self.cold_flow = np.clip(cold_flow, 0.0, self.max_flow_rate)
        if dump_flow is not None:
            self.dump_flow = np.clip(dump_flow, 0.0, self.max_dump_flow_rate)
        
        # Update supply temperatures if provided
        if hot_supply_temp is not None:
            self.hot_supply_temp = np.clip(hot_supply_temp, self.temp_min, self.temp_max)
        if cold_supply_temp is not None:
            self.cold_supply_temp = np.clip(cold_supply_temp, self.temp_min, self.temp_max)
        
        # Apply drift or use direct values
        if disable_drift:
            hot_flow_effective = self.hot_flow
            cold_flow_effective = self.cold_flow
            dump_flow_effective = self.dump_flow
        else:
            # Introduce slow drift/instability in supplies
            self.hot_supply_temp = np.clip(
                self.hot_supply_temp + np.random.normal(0.0, self.temp_drift_std),
                self.temp_min,
                self.temp_max
            )
            self.cold_supply_temp = np.clip(
                self.cold_supply_temp + np.random.normal(0.0, self.temp_drift_std),
                self.temp_min,
                self.temp_max
            )
            
            # Effective flows after supply noise
            hot_flow_effective = np.clip(
                self.hot_flow * (1.0 + np.random.normal(0.0, self.flow_drift_std)),
                0.0,
                self.max_flow_rate
            )
            cold_flow_effective = np.clip(
                self.cold_flow * (1.0 + np.random.normal(0.0, self.flow_drift_std)),
                0.0,
                self.max_flow_rate
            )
            dump_flow_effective = np.clip(
                self.dump_flow * (1.0 + np.random.normal(0.0, self.flow_drift_std)),
                0.0,
                self.max_dump_flow_rate
            )
        
        total_inflow = hot_flow_effective + cold_flow_effective
        inflow_volume = total_inflow * self.dt
        dump_volume = dump_flow_effective * self.dt
        
        # Avoid complete empty tank
        previous_volume = max(self.volume, 1e-6)
        
        if total_inflow > 0.001:
            mixed_temp = (
                (hot_flow_effective * self.hot_supply_temp + 
                 cold_flow_effective * self.cold_supply_temp) / max(total_inflow, 1e-6)
            )
        else:
            mixed_temp = self.current_temp
        
        # Energy balance with dumping and inflow
        retained_energy = self.current_temp * max(previous_volume - dump_volume, 0.0)
        added_energy = mixed_temp * inflow_volume
        self.volume = np.clip(previous_volume - dump_volume + inflow_volume, 0.01, self.tank_capacity)
        self.current_temp = (retained_energy + added_energy) / self.volume
        
        # Natural cooling toward ambient
        self.current_temp = (
            self.current_temp - self.mixed_water_cooling_rate * (self.current_temp - self.ambient_temp)
        )
        self.current_temp = float(np.clip(self.current_temp, self.temp_min, self.temp_max))
        
        self.step_count += 1
        self.temperature_history.append(self.current_temp)

        volume_ratio = self.volume / self.tank_capacity
        outputs = self._build_outputs_for_reward(volume_ratio)
        goal = {"target_temp": self.target_temp, "target_volume_ratio": [0.8, 0.85]}
        observation = self._get_observation()

        from rewards import evaluate_reward
        reward = evaluate_reward(
            self.rewards_config,
            outputs,
            goal,
            list(observation),
            self.step_count,
            self.max_steps,
        )

        temp_error = abs(self.current_temp - self.target_temp)
        # Check if done - SUCCESS requires BOTH temperature AND volume in ideal range (80-85%)
        temp_success = temp_error < 0.1
        volume_success = volume_ratio >= 0.80 and volume_ratio <= 0.85  # Tank must be in ideal range (80-85%)
        terminated = temp_success and volume_success  # Success: correct temp AND volume in ideal range
        truncated = self.step_count >= self.max_steps

        observation = self._get_observation()
        info = {
            "temperature": self.current_temp,
            "temp_error": temp_error,
            "hot_flow": self.hot_flow,
            "cold_flow": self.cold_flow,
            "dump_flow": self.dump_flow,
            "volume": self.volume,
            "volume_ratio": volume_ratio,
            "hot_supply_temp": self.hot_supply_temp,
            "cold_supply_temp": self.cold_supply_temp,
        }

        return observation, reward, terminated, truncated, info

    def _build_outputs_for_reward(self, volume_ratio: float) -> dict:
        """Build outputs-like dict from internal state for reward evaluator."""
        tank_id = "mixer_tank"
        hot_id = cold_id = dump_id = None
        if self.process_graph:
            for u in self.process_graph.units:
                vid = u.id.lower()
                if u.type == "Tank":
                    tank_id = u.id
                elif u.type == "Valve" and u.controllable:
                    if "hot" in vid:
                        hot_id = u.id
                    elif "cold" in vid:
                        cold_id = u.id
                    elif "dump" in vid:
                        dump_id = u.id
        hot_id = hot_id or "hot_valve"
        cold_id = cold_id or "cold_valve"
        dump_id = dump_id or "dump_valve"

        outputs = {
            tank_id: {
                "temp": self.current_temp,
                "volume": self.volume,
                "volume_ratio": volume_ratio,
            },
            hot_id: {"flow": self.hot_flow},
            cold_id: {"flow": self.cold_flow},
            dump_id: {"flow": self.dump_flow},
        }
        return outputs

    def _sensor_id_to_value(self, sensor_id: str) -> float:
        """Map a sensor unit id to normalized observation value (0–1) for thermodynamic env."""
        sid = sensor_id.lower()
        if "hot" in sid and "thermometer" in sid:
            return float(np.clip(self.hot_supply_temp / self.temp_max, 0.0, 1.0))
        if "cold" in sid and "thermometer" in sid:
            return float(np.clip(self.cold_supply_temp / self.temp_max, 0.0, 1.0))
        if "tank" in sid and "thermometer" in sid:
            return float(np.clip(self.current_temp / self.temp_max, 0.0, 1.0))
        if "thermometer" in sid:
            return float(np.clip(self.current_temp / self.temp_max, 0.0, 1.0))
        if "water_level" in sid or "volume" in sid:
            return float(np.clip(self.volume / self.tank_capacity, 0.0, 1.0))
        return float(np.clip(self.current_temp / self.temp_max, 0.0, 1.0))

    def _get_observation(self):
        """Convert internal state to observation vector (from graph wiring or legacy 7-dim)."""
        if self._observation_input_ids:
            return np.array(
                [self._sensor_id_to_value(uid) for uid in self._observation_input_ids],
                dtype=np.float32
            )
        normalized_time = self.step_count / self.max_steps
        return np.array([
            self.current_temp / self.temp_max,
            self.target_temp / self.temp_max,
            self.hot_flow / self.max_flow_rate,
            self.cold_flow / self.max_flow_rate,
            self.dump_flow / self.max_dump_flow_rate,
            normalized_time,
            self.volume / self.tank_capacity
        ], dtype=np.float32)
    
    def render(self):
        """Simple text rendering of current state."""
        if self.render_mode == "human":
            print(f"Step: {self.step_count}, "
                  f"Temp: {self.current_temp:.2f}°C (target: {self.target_temp}°C), "
                  f"Hot: {self.hot_flow:.2f} ({self.hot_supply_temp:.1f}°C), "
                  f"Cold: {self.cold_flow:.2f} ({self.cold_supply_temp:.1f}°C), "
                  f"Dump: {self.dump_flow:.2f}, "
                  f"Vol: {self.volume:.2f}, "
                  f"Error: {abs(self.current_temp - self.target_temp):.2f}°C")
