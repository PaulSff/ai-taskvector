"""Office native environment"""

from environments.native.office.loader import load_office_env
from environments.native.office.spec import OfficeEnvironmentSpec

__all__ = ["OfficeEnvironmentSpec", "load_office_env"]
