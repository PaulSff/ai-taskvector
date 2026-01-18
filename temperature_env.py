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
                 dt=0.1,
                 max_steps=200,
                 render_mode=None):
        super().__init__()
        
        self.target_temp = target_temp
        self.initial_temp = initial_temp
        self.hot_water_temp = hot_water_temp
        self.cold_water_temp = cold_water_temp
        self.max_flow_rate = max_flow_rate
        self.dt = dt  # Time step in seconds
        self.max_steps = max_steps
        self.render_mode = render_mode
        
        # State: [temperature, hot_flow, cold_flow, normalized_time]
        self.observation_space = spaces.Box(
            low=np.array([0.0, 0.0, 0.0, 0.0], dtype=np.float32),
            high=np.array([100.0, 1.0, 1.0, 1.0], dtype=np.float32),
            dtype=np.float32
        )
        
        # Action: [hot_valve_change, cold_valve_change] (normalized -1 to 1)
        self.action_space = spaces.Box(
            low=np.array([-1.0, -1.0], dtype=np.float32),
            high=np.array([1.0, 1.0], dtype=np.float32),
            dtype=np.float32
        )
        
        # Internal state
        self.current_temp = None
        self.hot_flow = None
        self.cold_flow = None
        self.step_count = None
        self.temperature_history = []
        
    def reset(self, seed=None, options=None):
        super().reset(seed=seed)
        
        # Initialize state
        self.current_temp = self.initial_temp
        self.hot_flow = 0.0
        self.cold_flow = 0.0
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
        hot_change = action[0] * 0.1  # Max 10% change per step
        cold_change = action[1] * 0.1
        
        self.hot_flow = np.clip(self.hot_flow + hot_change, 0.0, self.max_flow_rate)
        self.cold_flow = np.clip(self.cold_flow + cold_change, 0.0, self.max_flow_rate)
        
        # Calculate new temperature using mixing formula
        # Simplified: weighted average based on flow rates
        total_flow = self.hot_flow + self.cold_flow
        
        if total_flow > 0.001:  # Avoid division by zero
            # Mixing formula: weighted average of temperatures
            mixed_temp = (
                (self.hot_flow * self.hot_water_temp + 
                 self.cold_flow * self.cold_water_temp) / total_flow
            )
            
            # Update current temperature (with some inertia/smoothing)
            # This simulates the mixing process
            alpha = 0.3  # Mixing rate
            self.current_temp = (
                alpha * mixed_temp + (1 - alpha) * self.current_temp
            )
        else:
            # No flow - temperature drifts toward room temperature
            room_temp = 20.0
            self.current_temp = 0.99 * self.current_temp + 0.01 * room_temp
        
        self.step_count += 1
        self.temperature_history.append(self.current_temp)
        
        # Calculate reward
        # Primary reward: negative of temperature error
        temp_error = abs(self.current_temp - self.target_temp)
        reward = -temp_error
        
        # Bonus for being close to target
        if temp_error < 0.5:
            reward += 10.0
        elif temp_error < 1.0:
            reward += 5.0
        
        # Small penalty for excessive flow (energy efficiency)
        reward -= 0.01 * (self.hot_flow + self.cold_flow)
        
        # Check if done
        terminated = temp_error < 0.1  # Success: within 0.1°C
        truncated = self.step_count >= self.max_steps  # Timeout
        
        observation = self._get_observation()
        info = {
            "temperature": self.current_temp,
            "temp_error": temp_error,
            "hot_flow": self.hot_flow,
            "cold_flow": self.cold_flow,
        }
        
        return observation, reward, terminated, truncated, info
    
    def _get_observation(self):
        """Convert internal state to observation vector."""
        normalized_time = self.step_count / self.max_steps
        return np.array([
            self.current_temp / 100.0,  # Normalize temperature
            self.hot_flow / self.max_flow_rate,
            self.cold_flow / self.max_flow_rate,
            normalized_time
        ], dtype=np.float32)
    
    def render(self):
        """Simple text rendering of current state."""
        if self.render_mode == "human":
            print(f"Step: {self.step_count}, "
                  f"Temp: {self.current_temp:.2f}°C (target: {self.target_temp}°C), "
                  f"Hot: {self.hot_flow:.2f}, Cold: {self.cold_flow:.2f}, "
                  f"Error: {abs(self.current_temp - self.target_temp):.2f}°C")

