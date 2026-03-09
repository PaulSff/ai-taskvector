"""
Environment source: Gymnasium, External, or Native.
"""
from enum import Enum


class EnvSource(str, Enum):
    """Where dynamics come from: Gymnasium API, external simulator (wrapper), or our native envs."""

    GYMNASIUM = "gymnasium"
    EXTERNAL = "external"
    NATIVE = "native"
