"""Environment "taskvector" units (scaffolded by list_environment). See README.md."""
from __future__ import annotations

import logging

from units.env_loaders import register_env_loader
from units.registry import UNIT_REGISTRY
from units.taskvector.agent_orchestrator import register_agent_orchestrator
from units.taskvector.clone_role import register_clone_role_unit
from units.taskvector.export_workflow import register_export_workflow
from units.taskvector.import_workflow import register_import_workflow
from units.taskvector.list_environment import register_list_environment
from units.taskvector.list_unit import register_list_unit
from units.taskvector.load_workflow import register_load_workflow
from units.taskvector.process_agent import register_process_agent
from units.taskvector.prompt import register_prompt
from units.taskvector.run_rl_training import register_run_rl_training
from units.taskvector.run_workflow import register_run_workflow
from units.taskvector.save_workflow import register_save_workflow

logger = logging.getLogger(__name__)

_TASKVECTOR_TYPE_NAMES = (
   "CloneRole",
   "ExportWorkflow",
   "Import_workflow",
   "list_environment",
   "list_unit",
   "LoadWorkflow",
   "RunRLTraining",
   "RunWorkflow",
   "SaveWorkflow",
   "AgentOrchestrator",
   "ProcessAgent",
   "Prompt"
)

def register_taskvector_units() -> None:
    """Register units for taskvector. Add register_* calls as you add units under units/taskvector/."""
    register_clone_role_unit()
    register_export_workflow()
    register_import_workflow()
    register_list_environment()
    register_list_unit()
    register_load_workflow()
    register_run_rl_training()
    register_run_workflow()
    register_save_workflow()
    register_agent_orchestrator()
    register_process_agent()
    register_prompt()

    for name in _TASKVECTOR_TYPE_NAMES:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["taskvector"]

def _register_taskvector_env_loader() -> None:
    try:
        from units.env_loaders import register_env_loader
    except ImportError:
        logger.info("env_loaders not available; cannot register taskvector env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_env_loader for taskvector")
        raise

    try:
        from units.taskvector import register_taskvector_units
    except ImportError:
        logger.info("units.taskvector not available; cannot register taskvector env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_taskvector_units for taskvector")
        raise

    try:
        register_env_loader("taskvector", register_taskvector_units)
    except Exception:
        logger.exception("Failed to register taskvector env loader")
        raise

_register_taskvector_env_loader()


register_env_loader("taskvector", register_taskvector_units)

__all__ = ["register_taskvector_units"]
