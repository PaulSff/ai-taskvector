"""
Base wrapper for external simulators: expose gym.Env interface.
Subclass and implement _connect(), _obs_from_sim(), _send_action(), etc.
"""
from typing import Any

import gymnasium as gym
from gymnasium import spaces
import numpy as np


class BaseExternalWrapper(gym.Env):
    """
    Base class for wrapping an external simulator as a Gymnasium env.
    Subclasses implement _connect(), _get_obs(), _send_action(), _reward(), etc.
    """

    metadata = {"render_modes": []}

    def __init__(self, config: dict[str, Any], render_mode: str | None = None):
        super().__init__()
        self.config = config
        self.render_mode = render_mode
        self._connected = False
        # Subclasses set observation_space and action_space in _connect()
        self.observation_space = spaces.Box(
            low=-np.inf, high=np.inf, shape=(1,), dtype=np.float32
        )
        self.action_space = spaces.Box(
            low=-1.0, high=1.0, shape=(1,), dtype=np.float32
        )

    def _connect(self) -> None:
        """Connect to or instantiate the external simulator. Set observation_space, action_space."""
        raise NotImplementedError

    def _get_obs(self) -> np.ndarray:
        """Read current observation from simulator."""
        raise NotImplementedError

    def _send_action(self, action: np.ndarray) -> None:
        """Send action to simulator (one step)."""
        raise NotImplementedError

    def _reward(self) -> float:
        """Compute reward for current state."""
        raise NotImplementedError

    def _done(self) -> tuple[bool, bool]:
        """Return (terminated, truncated)."""
        return False, False

    def reset(
        self, *, seed: int | None = None, options: dict[str, Any] | None = None
    ) -> tuple[np.ndarray, dict[str, Any]]:
        super().reset(seed=seed)
        if not self._connected:
            self._connect()
            self._connected = True
        # Subclasses may reset simulator state here
        obs = self._get_obs()
        return obs, {}

    def step(
        self, action: np.ndarray
    ) -> tuple[np.ndarray, float, bool, bool, dict[str, Any]]:
        self._send_action(action)
        obs = self._get_obs()
        reward = self._reward()
        terminated, truncated = self._done()
        return obs, reward, terminated, truncated, {}
