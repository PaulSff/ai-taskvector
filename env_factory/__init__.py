"""
Env factory: build Gymnasium env from canonical process graph and goal config.
Consumes canonical schemas only (use normalizer for any external format).
"""
from env_factory.factory import build_env

__all__ = ["build_env"]
