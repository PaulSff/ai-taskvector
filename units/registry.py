"""
Unit registry: maps unit type strings to implementations (ComfyUI-style NODE_CLASS_MAPPINGS).

Each UnitSpec defines:
- input_ports: ordered list of (port_name, port_type) for graph wiring
- output_ports: ordered list of (port_name, port_type)
- step_fn: callable(params, inputs, state, dt) -> (outputs, new_state)
- optional: export_template for code_block generation
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Callable

PortSpec = tuple[str, str]  # (name, type e.g. "float", "flow", "temp")


@dataclass
class UnitSpec:
    """
    Specification for a unit type: ports, step function, and optional metadata.

    step_fn(params: dict, inputs: dict, state: dict, dt: float) -> (outputs: dict, new_state: dict)
    - params: from Unit.params (type-specific config)
    - inputs: resolved from connections {port_name: value}
    - state: unit's internal state (mutable between steps)
    - dt: time step

    controllable: True if this unit is an action/control input (e.g. Valve). Used by the
    normalizer when importing flows; see is_controllable_type().
    """

    type_name: str
    input_ports: list[PortSpec] = field(default_factory=list)
    output_ports: list[PortSpec] = field(default_factory=list)
    step_fn: Callable[..., tuple[dict[str, Any], dict[str, Any]]] | None = None
    export_template: str | None = None  # for code_block / graph export (future)
    controllable: bool = False
    role: str | None = None  # optional semantic role (e.g. "step_driver", "join", "switch") for type-agnostic lookup
    environment_tags: list[str] | None = None  # e.g. ["thermodynamic"], ["data_bi"], ["canonical"], ["RL training"]; used for env inference
    environment_tags_are_agnostic: bool = False  # if True, these tags do not require add_environment to show (e.g. canonical, RL training)
    description: str | None = None  # short one-sentence description for UI and tooling
    pipeline: bool = False  # True for pipeline types (RLGym, RLOracle, RLSet, LLMSet); use add_pipeline, not add_unit
    template_path: str | None = None  # For pipeline types: path to workflow JSON relative to repo root (used by pipeline_templates loader)
    runtime_scope: str | None = None  # "canonical" (native only), "external" (external only), or None/"both"
    code_block_driven: bool = False  # True for function/pyflow types: executor runs graph code_block; step_fn may be None
    # Repo-relative paths for Workflow Designer Units Library (read_file via RAG index); optional explicit override.
    library_source_path: str | None = None  # e.g. units/thermodynamic/tank/tank.py
    library_docs_path: str | None = None  # e.g. units/thermodynamic/tank/README.md

    def __post_init__(self) -> None:
        if self.step_fn is None and not self.code_block_driven:
            raise ValueError(f"UnitSpec {self.type_name} must have step_fn or code_block_driven=True")


UNIT_REGISTRY: dict[str, UnitSpec] = {}


def register_unit(spec: UnitSpec) -> None:
    """Register a unit type. Overwrites if already present."""
    UNIT_REGISTRY[spec.type_name] = spec


def get_unit_spec(type_name: str) -> UnitSpec | None:
    """Return UnitSpec for type_name or None if not registered."""
    return UNIT_REGISTRY.get(type_name)


def get_type_by_role(role: str) -> str | None:
    """Return first registered type_name whose UnitSpec has the given role, or None. For type-agnostic lookup."""
    for spec in UNIT_REGISTRY.values():
        if spec.role == role:
            return spec.type_name
    return None


def is_controllable_type(type_name: str) -> bool:
    """Return True if the unit type is registered and marked controllable (e.g. Valve). Used by the normalizer."""
    spec = get_unit_spec(type_name)
    return spec.controllable if spec else False


def ensure_full_unit_registry() -> None:
    """
    Populate UNIT_REGISTRY for workflow execution: env-agnostic units, canonical workflow units,
    and every environment loader (thermodynamic, data_bi, pyflow, …). Idempotent.

    Called from runtime.run.run_workflow at startup so UnitsLibrary and other units see the full
    catalog without a separate \"bootstrap\" node in each workflow graph.
    """
    try:
        from units.register_env_agnostic import register_env_agnostic_units

        register_env_agnostic_units()
    except Exception:
        pass
    try:
        from units.canonical import register_canonical_units

        register_canonical_units()
    except Exception:
        pass
    try:
        from units.env_loaders import ensure_all_environment_units_registered

        ensure_all_environment_units_registered()
    except Exception:
        pass
