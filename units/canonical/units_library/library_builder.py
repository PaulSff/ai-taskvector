"""
Units Library builder: unit types + descriptions filtered by runtime and environment.

All type lists and runtime rules are derived from the unit registry (UnitSpec.pipeline, runtime_scope,
environment_tags). No hardcoded type names. Self-contained within the UnitsLibrary canonical unit.
"""
from __future__ import annotations


def _ensure_units_registered_for_library() -> None:
    """Ensure env-agnostic and all environment units are registered from registry/factory (no hardcoded env names)."""
    try:
        from units.register_env_agnostic import register_env_agnostic_units

        register_env_agnostic_units()
    except Exception:
        pass
    try:
        from units.env_loaders import ensure_all_environment_units_registered

        ensure_all_environment_units_registered()
    except Exception:
        pass


def format_units_library_for_prompt(graph_summary_dict: dict) -> str:
    """
    Build "Units Library" text: unit types and pipeline types with descriptions, filtered by
    runtime (origin) and environment. For the Workflow Designer system prompt.

    - Runtime filter: external → exclude RLGym; canonical → exclude RLOracle. Process units
      deployable to external (thermodynamic, data_bi) are included; canonical-only topology
      units (Join, Switch, etc.) excluded when external.
    - Environment filter: when graph has environments set, include units whose tags intersect
      and environment-agnostic types. When environments is missing or empty, show ONLY
      canonical and environment-agnostic units (so the assistant is not overwhelmed; use
      add_environment to add an environment first).
    - Function: env-agnostic, always shown for all environments and runtimes (canonical + external).
    - PyFlow units (constant, branch, reroute, etc.): only shown when graph has environment "pyflow".
    """
    from core.normalizer.runtime_detector import is_external_runtime
    from units.registry import UNIT_REGISTRY, get_unit_spec

    _ensure_units_registered_for_library()

    runtime_external = is_external_runtime(graph_summary_dict)
    env_list = graph_summary_dict.get("environments")
    if env_list is None:
        env_list = []
    if isinstance(env_list, list):
        env_set = {str(e).strip().lower() for e in env_list if e}
    else:
        env_set = set()
    # When no environments: only canonical + environment-agnostic. When environments set: env units + agnostic.
    env_set_empty_means_restrict = not env_set  # true when graph has no environments

    unit_lines: list[str] = []
    pipeline_lines: list[str] = []

    for type_name, spec in sorted(UNIT_REGISTRY.items(), key=lambda x: x[0].lower()):
        tags = spec.environment_tags or []
        tag_set = {t.strip().lower() for t in tags if t}
        scope = getattr(spec, "runtime_scope", None)  # "canonical" | "external" | None (both)
        is_pipeline = getattr(spec, "pipeline", False)

        # Runtime filter from registry: exclude canonical-only when external, external-only when canonical.
        if runtime_external and scope == "canonical":
            continue
        if not runtime_external and scope == "external":
            continue

        # Environment filter: when graph has no environments, only canonical + env-agnostic; when set, env units + agnostic.
        # Derive from registry: all tags, and agnostic tags (tags on specs with environment_tags_are_agnostic=True).
        _all_tags: set[str] = set()
        _agnostic_tags: set[str] = set()
        for _spec in UNIT_REGISTRY.values():
            for _t in _spec.environment_tags or []:
                if _t and str(_t).strip():
                    _tag = str(_t).strip().lower()
                    _all_tags.add(_tag)
                    if getattr(_spec, "environment_tags_are_agnostic", False):
                        _agnostic_tags.add(_tag)
        runtime_env_tags = _all_tags - _agnostic_tags
        if env_set_empty_means_restrict:
            # No environments on graph: show only canonical and environment-agnostic (no Source, Valve, etc.).
            if tag_set and (tag_set & runtime_env_tags):
                continue
        else:
            # Graph has environments: include unit if in env set, or canonical (native), or env-agnostic.
            if tag_set:
                if env_set & tag_set:
                    pass  # unit in one of the graph's environments
                elif not runtime_external and "canonical" in tag_set:
                    pass  # canonical topology units for native runtime
                elif not (tag_set & runtime_env_tags):
                    pass  # environment-agnostic (only canonical / RL training)
                else:
                    continue
            # empty tag_set => environment-agnostic; include

        desc = spec.description or type_name
        if is_pipeline:
            pipeline_lines.append(f"{type_name} : {desc}")
        else:
            unit_lines.append(f"{type_name} : {desc}")

    # Ensure "function" is always listed (env-agnostic, all runtimes); PyFlow types only when graph has pyflow env
    seen = {line.split(" : ")[0].strip() for line in unit_lines}
    if "function" not in seen:
        spec = get_unit_spec("function")
        desc = (spec.description or "function") if spec else "function"
        unit_lines.append(f"function : {desc}")

    try:
        from units.env_loaders import known_environment_tags
        known_envs = known_environment_tags()
    except Exception:
        known_envs = []
    graph_envs = sorted(env_set) if env_set else []

    if not unit_lines and not pipeline_lines and not known_envs:
        return ""

    parts = ["---", "Units Library available for this graph:", ""]
    if known_envs:
        parts.append("Environments (use add_environment to add to graph): " + ", ".join(known_envs))
        if graph_envs:
            parts.append("Graph environments: " + ", ".join(graph_envs))
        else:
            parts.append("Graph environments: (none — only canonical and environment-agnostic units shown)")
        parts.append("")
    if unit_lines:
        parts.append("\n".join(unit_lines))
        parts.append("")
    if pipeline_lines:
        parts.append("--")
        parts.append("\n".join(pipeline_lines))
    parts.append("")
    parts.append("---")
    return "\n".join(parts)
