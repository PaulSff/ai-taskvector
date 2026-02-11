"""
External runtime I/O semantics for RL training.

When training against an external runtime (Node-RED, EdgeLinkd, etc.) we exchange vectors:
- Step:  { "action": [float, ...] }
- Reset: { "reset": true }
- Reply: { "observation": [float, ...], "reward": float, "done": bool }

`obs_shape` / `action_shape` define only vector sizes. This module defines first-class schemas
for the *meaning* of each dimension (names + optional transforms/ranges) so semantics are explicit.
"""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ObservationSpecItem(BaseModel):
    """
    One element of the observation vector.

    The external runtime returns observation values; optional transforms can be applied client-side
    (adapter) to scale/offset/clip before the RL policy sees them.
    """

    name: str = Field(..., description="Human-readable feature name (defines vector index order).")
    description: str | None = Field(default=None, description="Optional description for UI/docs.")
    scale: float = Field(default=1.0, description="Optional scale applied to raw value: out = raw * scale + offset.")
    offset: float = Field(default=0.0, description="Optional offset applied to raw value: out = raw * scale + offset.")
    clip_min: float | None = Field(default=None, description="Optional minimum clip after transform.")
    clip_max: float | None = Field(default=None, description="Optional maximum clip after transform.")


class ActionSpecItem(BaseModel):
    """
    One element of the action vector.

    RL algorithms typically operate on normalized [-1, 1] actions. When min/max are provided,
    adapters can map normalized actions to the target range before sending to the runtime.
    """

    name: str = Field(..., description="Human-readable action name (defines vector index order).")
    description: str | None = Field(default=None, description="Optional description for UI/docs.")
    min: float | None = Field(default=None, description="Optional lower bound of real actuator range.")
    max: float | None = Field(default=None, description="Optional upper bound of real actuator range.")


class ExternalIOSpec(BaseModel):
    """
    Full I/O semantics specification for an external runtime adapter.
    Stored under TrainingConfig.environment.adapter_config.
    """

    observation_spec: list[ObservationSpecItem] = Field(default_factory=list, description="Ordered observation vector spec.")
    action_spec: list[ActionSpecItem] = Field(default_factory=list, description="Ordered action vector spec.")

    def obs_dim(self) -> int:
        return len(self.observation_spec)

    def action_dim(self) -> int:
        return len(self.action_spec)

    @staticmethod
    def from_adapter_config(cfg: dict[str, Any]) -> ExternalIOSpec:
        """Parse spec from adapter_config dict (missing keys -> empty lists)."""
        raw_obs = cfg.get("observation_spec") or []
        raw_act = cfg.get("action_spec") or []
        return ExternalIOSpec(
            observation_spec=[ObservationSpecItem.model_validate(x) for x in raw_obs] if isinstance(raw_obs, list) else [],
            action_spec=[ActionSpecItem.model_validate(x) for x in raw_act] if isinstance(raw_act, list) else [],
        )

