"""Web native environment: browser, web_search units (Python-only)."""

from environments.native.web.loader import load_web_env
from environments.native.web.spec import WebEnvSpec

__all__ = ["load_web_env", "WebEnvSpec"]
