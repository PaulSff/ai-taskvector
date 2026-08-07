"""Environment "coding" units (scaffolded by list_environment). See README.md."""
from __future__ import annotations

import logging

from units.coding.delete import register_delete_unit
from units.coding.edit_file import register_edit_file_unit
from units.coding.make_dir import register_make_dir_unit
from units.coding.new_file import register_new_file_writer
from units.coding.rename import register_rename_unit
from units.env_loaders import register_env_loader
from units.registry import UNIT_REGISTRY

logger = logging.getLogger(__name__)

_CODING_TYPE_NAMES = (
   "NewFile",
   "EditFile",
   "MakeDir",
   "Delete",
   "Rename"
)

def register_coding_units() -> None:
    """Register units for coding. Add register_* calls as you add units under units/coding/."""
    register_new_file_writer()
    register_edit_file_unit()
    register_make_dir_unit()
    register_delete_unit()
    register_rename_unit()

    for name in _CODING_TYPE_NAMES:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["coding"]


def _register_coding_env_loader() -> None:
    try:
        from units.env_loaders import register_env_loader
    except ImportError:
        logger.info("env_loaders not available; cannot register coding env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_env_loader for coding")
        raise

    try:
        from units.coding import register_coding_units
    except ImportError:
        logger.info("units.coding not available; cannot register coding env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_coding_units for coding")
        raise

    try:
        register_env_loader("coding", register_coding_units)
    except Exception:
        logger.exception("Failed to register coding env loader")
        raise

_register_coding_env_loader()


register_env_loader("coding", register_coding_units)

__all__ = ["register_coding_units"]
