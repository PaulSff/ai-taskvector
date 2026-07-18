"""Time native environment: iCalendar .ics and other integrations."""

from environments.native.time.loader import load_time_env
from environments.native.time.spec import TimeEnvironmentSpec

__all__ = ["load_time_env", "TimeEnvironmentSpec"]
