"""Canonical (native runtime) units: training flow + workflow units (Inject, ApplyEdits, ProcessAgent, graph_edit, trigger). StepDriver/StepRewards live in env_agnostic (supported on any runtime)."""

from units.canonical.aggregate import register_aggregate
from units.canonical.apply_edits import register_apply_edits
from units.canonical.apply_training_config_edits import (
    register_apply_training_config_edits,
)
from units.canonical.chameleon import register_chameleon
from units.canonical.debug import register_debug
from units.canonical.delegate_request import register_delegate_request
from units.canonical.graph_diff import register_graph_diff
from units.canonical.graph_edit import register_graph_edit_flow_units
from units.canonical.graph_getters import register_lookup_graph_units
from units.canonical.graph_summary import register_graph_summary
from units.canonical.join import register_join
from units.canonical.normalize_graph import register_normalize_graph
from units.canonical.payload_transform import register_payload_transform
from units.canonical.random import register_random
from units.canonical.router import register_router
from units.canonical.runtime_label import register_runtime_label
from units.canonical.split import register_split
from units.canonical.switch import register_switch
from units.canonical.template import register_template
from units.canonical.training_config_parser import register_training_config_parser
from units.canonical.trigger import register_workflow_trigger
from units.canonical.units_library import register_units_library
from units.canonical.validate_graph_to_apply import register_validate_graph_to_apply
from units.pyflow import register_pyflow_units


def register_canonical_units() -> None:
    """Register canonical units (native runtime only): training flow + Inject, ApplyEdits, ProcessAgent, trigger, graph_edit. StepDriver/StepRewards registered from env_agnostic (any runtime)."""
    from units.registry import UNIT_REGISTRY

    register_split()
    register_join()
    register_aggregate()
    register_switch()
    register_random()
    register_pyflow_units()  # also registered as env "pyflow" loader for filtering
    register_apply_edits()
    register_graph_diff()
    register_graph_summary()
    register_delegate_request()
    register_workflow_trigger()
    register_graph_edit_flow_units()  # Inject + add_unit, connect, disconnect, etc.
    register_units_library()
    register_debug()
    register_template()
    register_runtime_label()
    register_normalize_graph()
    register_validate_graph_to_apply()
    register_training_config_parser()
    register_apply_training_config_edits()
    register_router()
    register_payload_transform()
    register_lookup_graph_units()
    register_chameleon()

    canonical_type_names = (
        "Join",
        "Aggregate",
        "Split",
        "Switch",
        "Router",
        "HttpIn",
        "HttpResponse",
        "Random",
        "Inject",
        "Template",
        "ApplyEdits",
        "GraphDiff",
        "GraphSummary",
        "UnitsLibrary",
        "Debug",
        "PayloadTransform",
        "Chameleon",
        "delegate_request",
        "WorkflowTrigger",
        "LoadWorkflow",
        "RuntimeLabel",
        "NormalizeGraph",
        "ValidateGraphToApply",
        "TrainingConfigParser",
        "ApplyTrainingConfigEdits",
        "add_unit",
        "add_pipeline",
        "remove_unit",
        "connect",
        "disconnect",
        "replace_unit",
        "replace_graph",
        "add_code_block",
        "add_comment",
        "add_environment",
        "no_edit",
        "todo_list",
        "lookup_graph_units",
    )
    for name in canonical_type_names:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["canonical"]
            spec.environment_tags_are_agnostic = True
            spec.runtime_scope = "canonical"


__all__ = ["register_canonical_units"]
