"""Semantics native environment: language detection and related units."""

from environments.native.semantics.loader import load_semantics_env
from environments.native.semantics.spec import SemanticsEnvironmentSpec

__all__ = ["SemanticsEnvironmentSpec", "load_semantics_env"]
