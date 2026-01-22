"""
Temperature Control Environment for Reinforcement Learning
Simulates mixing hot and cold water to reach a target temperature.
"""
import gymnasium as gym
from gymnasium import spaces
import numpy as np


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
                 randomize_params=False):
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
        
        # Tank properties
        self.tank_capacity = 1.0  # normalized volume
        self.ambient_temp = 20.0
        self.temp_min = 0.0
        self.temp_max = 100.0
        
        # Supply instability parameters
        self.temp_drift_std = 0.2  # °C change per step
        self.flow_drift_std = 0.02  # 2% flow noise
        
        # State: [temperature, hot_flow, cold_flow, dump_flow, normalized_time, volume]
        self.observation_space = spaces.Box(
            low=np.array([0.0, 0.0, 0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            high=np.array([1.0, 1.0, 1.0, 1.0, 1.0, 1.0], dtype=np.float32),
            dtype=np.float32
        )
        
        # Action: [hot_valve_change, cold_valve_change, dump_valve_change] (normalized -1 to 1)
        self.action_space = spaces.Box(
            low=np.array([-1.0, -1.0, -1.0], dtype=np.float32),
            high=np.array([1.0, 1.0, 1.0], dtype=np.float32),
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
        
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        
        # Randomize physics within safe bounds if requested
        randomize = (options and options.get("randomize")) or self.randomize_params
        if randomize:
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
    
    def step(self, action):
        # Clip actions to valid range
        action = np.clip(action, self.action_space.low, self.action_space.high)
        
        # Update flow rates (action is change in valve position)
        # Map action from [-1, 1] to flow rate change
        hot_change = action[0] * 0.6  # Max 60% change per step
        cold_change = action[1] * 0.6
        dump_change = action[2] * 0.6
        
        self.hot_flow = np.clip(self.hot_flow + hot_change, 0.0, self.max_flow_rate)
        self.cold_flow = np.clip(self.cold_flow + cold_change, 0.0, self.max_flow_rate)
        self.dump_flow = np.clip(self.dump_flow + dump_change, 0.0, self.max_dump_flow_rate)
        
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
        
        # Calculate reward
        # Primary reward: negative of temperature error
        temp_error = abs(self.current_temp - self.target_temp)
        reward = -temp_error
        
        # Volume fullness reward (encourage reaching 80-85% range)
        volume_ratio = self.volume / self.tank_capacity
        volume_error = 0.8 - volume_ratio  # 0 when at 0.8, positive when below
        if volume_error > 0:
            reward -= 0.5 * volume_error  # Penalty for being below 80%
        
        # Bonus for being close to target temperature
        if temp_error < 0.5:
            reward += 10.0
        elif temp_error < 1.0:
            reward += 5.0
        
        # Bonus for being in the target volume range (80-85%)
        if volume_ratio >= 0.80 and volume_ratio <= 0.85:
            reward += 10.0  # Bonus for being in ideal range
        elif volume_ratio >= 0.75:
            reward += 5.0  # Bonus for getting close
        elif volume_ratio >= 0.70:
            reward += 2.0  # Small bonus for making progress
        
        # Penalty for exceeding the target range
        if volume_ratio > 0.85:
            excess_volume = volume_ratio - 0.85
            reward -= 2.0 * excess_volume  # Penalty for exceeding 85%
        
        # Large bonus for achieving both goals simultaneously
        if temp_error < 0.1 and volume_ratio >= 0.80 and volume_ratio <= 0.85:
            reward += 20.0  # Big bonus for success condition
        
        # Small penalty for excessive flow (energy efficiency)
        reward -= 0.01 * (self.hot_flow + self.cold_flow)
        
        # Strongly discourage unnecessary dumping
        reward -= 0.1 * self.dump_flow  # Base penalty for any dumping
        
        # Additional penalty for dumping when temperature is close to target (wasteful)
        if temp_error < 2.0 and self.dump_flow > 0.1:
            reward -= 0.5 * self.dump_flow  # Extra penalty for dumping when close to target
        
        # Bonus for keeping dump flow minimal (encourage efficient control)
        if self.dump_flow < 0.05:
            reward += 0.3  # Bonus for minimal/no dumping
        
        # Encourage efficient valve usage
        # Penalize excessive cold water when temperature is too low
        if self.current_temp < self.target_temp - 1.0:  # Too cold
            if self.cold_flow > 0.3:  # Using too much cold water
                reward -= 0.5 * (self.cold_flow - 0.3)  # Penalty for excessive cold water
            # Reward reducing cold water when temp is low
            if self.cold_flow < 0.2:
                reward += 0.2  # Small bonus for efficient cold water usage
        
        # Penalize excessive hot water when temperature is too high
        if self.current_temp > self.target_temp + 1.0:  # Too hot
            if self.hot_flow > 0.3:  # Using too much hot water
                reward -= 0.5 * (self.hot_flow - 0.3)  # Penalty for excessive hot water
        
        # Reward balanced valve usage (not maxing out one valve unnecessarily)
        # If one valve is near max and the other is low, suggest inefficiency
        if max(self.hot_flow, self.cold_flow) > 0.8 and min(self.hot_flow, self.cold_flow) < 0.2:
            # One valve maxed, other nearly closed - might be inefficient
            reward -= 0.1  # Small penalty to encourage exploring balanced strategies
        
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
        
        # Calculate reward (same as step() for consistency)
        temp_error = abs(self.current_temp - self.target_temp)
        reward = -temp_error
        
        # Volume fullness reward (encourage reaching 80-85% range)
        volume_ratio = self.volume / self.tank_capacity
        volume_error = 0.8 - volume_ratio  # 0 when at 0.8, positive when below
        if volume_error > 0:
            reward -= 0.5 * volume_error  # Penalty for being below 80%
        
        # Bonus for being close to target temperature
        if temp_error < 0.5:
            reward += 10.0
        elif temp_error < 1.0:
            reward += 5.0
        
        # Bonus for being in the target volume range (80-85%)
        if volume_ratio >= 0.80 and volume_ratio <= 0.85:
            reward += 10.0  # Bonus for being in ideal range
        elif volume_ratio >= 0.75:
            reward += 5.0  # Bonus for getting close
        elif volume_ratio >= 0.70:
            reward += 2.0  # Small bonus for making progress
        
        # Penalty for exceeding the target range
        if volume_ratio > 0.85:
            excess_volume = volume_ratio - 0.85
            reward -= 2.0 * excess_volume  # Penalty for exceeding 85%
        
        # Large bonus for achieving both goals simultaneously
        if temp_error < 0.1 and volume_ratio >= 0.80 and volume_ratio <= 0.85:
            reward += 20.0  # Big bonus for success condition
        
        # Small penalty for excessive flow (energy efficiency)
        reward -= 0.01 * (self.hot_flow + self.cold_flow)
        
        # Strongly discourage unnecessary dumping
        reward -= 0.1 * self.dump_flow  # Base penalty for any dumping
        
        # Additional penalty for dumping when temperature is close to target (wasteful)
        if temp_error < 2.0 and self.dump_flow > 0.1:
            reward -= 0.5 * self.dump_flow  # Extra penalty for dumping when close to target
        
        # Bonus for keeping dump flow minimal (encourage efficient control)
        if self.dump_flow < 0.05:
            reward += 0.3  # Bonus for minimal/no dumping
        
        # Encourage efficient valve usage (same as step())
        # Penalize excessive cold water when temperature is too low
        if self.current_temp < self.target_temp - 1.0:  # Too cold
            if self.cold_flow > 0.3:  # Using too much cold water
                reward -= 0.5 * (self.cold_flow - 0.3)  # Penalty for excessive cold water
            # Reward reducing cold water when temp is low
            if self.cold_flow < 0.2:
                reward += 0.2  # Small bonus for efficient cold water usage
        
        # Penalize excessive hot water when temperature is too high
        if self.current_temp > self.target_temp + 1.0:  # Too hot
            if self.hot_flow > 0.3:  # Using too much hot water
                reward -= 0.5 * (self.hot_flow - 0.3)  # Penalty for excessive hot water
        
        # Reward balanced valve usage (not maxing out one valve unnecessarily)
        if max(self.hot_flow, self.cold_flow) > 0.8 and min(self.hot_flow, self.cold_flow) < 0.2:
            reward -= 0.1  # Small penalty to encourage exploring balanced strategies
        
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
    
    def _get_observation(self):
        """Convert internal state to observation vector."""
        normalized_time = self.step_count / self.max_steps
        return np.array([
            self.current_temp / self.temp_max,  # Normalize temperature
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

