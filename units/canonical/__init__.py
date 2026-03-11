"""Canonical (native runtime) units: training flow + workflow units (Inject, ApplyEdits, ProcessAgent, graph_edit, grep, trigger). StepDriver/StepRewards live in env_agnostic (supported on any runtime)."""

from units.canonical.http_in import register_http_in
from units.pyflow import register_pyflow_units
from units.canonical.http_response import register_http_response
from units.canonical.join import register_join
from units.canonical.merge import register_merge
from units.canonical.prompt import register_prompt
from units.canonical.random import register_random
from units.canonical.split import register_split
from units.canonical.switch import register_switch
from units.canonical.apply_edits import register_apply_edits
from units.canonical.graph_diff import register_graph_diff
from units.canonical.graph_summary import register_graph_summary
from units.canonical.grep import register_grep
from units.canonical.trigger import register_workflow_trigger
from units.canonical.graph_edit import register_graph_edit_flow_units
from units.canonical.process_agent import register_process_agent
from units.canonical.units_library import register_units_library
from units.canonical.rag_search import register_rag_search
from units.canonical.format_rag_prompt import register_format_rag_prompt
from units.canonical.rag_update import register_rag_update
from units.canonical.create_file_on_rag import register_create_file_on_rag


def register_canonical_units() -> None:
    """Register canonical units (native runtime only): training flow + Inject, ApplyEdits, ProcessAgent, grep, trigger, graph_edit. StepDriver/StepRewards registered from env_agnostic (any runtime)."""
    from units.registry import UNIT_REGISTRY

    register_split()
    register_join()
    register_merge()
    register_prompt()
    register_switch()
    register_http_in()
    register_http_response()
    register_random()
    register_pyflow_units()  # also registered as env "pyflow" loader for filtering
    register_apply_edits()
    register_graph_diff()
    register_graph_summary()
    register_grep()
    register_workflow_trigger()
    register_graph_edit_flow_units()  # Inject + add_unit, connect, disconnect, etc.
    register_process_agent()
    register_units_library()
    register_rag_search()
    register_format_rag_prompt()
    register_rag_update()
    register_create_file_on_rag()

    canonical_type_names = (
        "Join", "Merge", "Prompt", "Split", "Switch", "HttpIn", "HttpResponse", "Random",
        "Inject", "ApplyEdits", "GraphDiff", "GraphSummary", "ProcessAgent", "UnitsLibrary", "RagSearch", "FormatRagPrompt", "RagUpdate", "CreateFileOnRag", "grep", "WorkflowTrigger",
        "add_unit", "add_pipeline", "remove_unit", "connect", "disconnect", "replace_unit", "replace_graph",
        "add_code_block", "add_comment", "add_environment", "no_edit", "todo_list",
    )
    for name in canonical_type_names:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["canonical"]
            spec.environment_tags_are_agnostic = True
            spec.runtime_scope = "canonical"


__all__ = ["register_canonical_units"]
