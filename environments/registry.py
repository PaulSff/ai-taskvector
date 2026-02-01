"""
Environment source: Gymnasium, External, or Custom.
"""
from enum import Enum


class EnvSource(str, Enum):
    """Where dynamics come from: Gymnasium API, external simulator (wrapper), or our custom envs."""

    GYMNASIUM = "gymnasium"
    EXTERNAL = "external"
    CUSTOM = "custom"
