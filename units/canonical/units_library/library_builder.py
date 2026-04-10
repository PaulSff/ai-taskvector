"""
Units Library builder: unit types + descriptions filtered by runtime and environment.

All type lists and runtime rules are derived from the unit registry (UnitSpec.pipeline, runtime_scope,
environment_tags). No hardcoded type names. Self-contained within the UnitsLibrary canonical unit.
"""
from __future__ import annotations

import inspect
from pathlib import Path


def _repo_root() -> Path:
    """Repository root (parent of ``units/``). Same depth as ``units/canonical/units_library`` → parents[3]."""
    return Path(__file__).resolve().parents[3]


def _infer_library_paths_from_step_fn(step_fn: object) -> tuple[str | None, str | None]:
    """
    Derive repo-relative paths to the implementing module and sibling README.md, if under ``units/``.
    """
    if step_fn is None or not callable(step_fn):
        return None, None
    try:
        mod = inspect.getmodule(step_fn)
        raw = getattr(mod, "__file__", None) if mod else None
        if not raw:
            return None, None
        py_file = Path(raw).resolve()
        repo = _repo_root()
        try:
            rel_py = py_file.relative_to(repo)
        except ValueError:
            return None, None
        rel_s = str(rel_py).replace("\\", "/")
        if not rel_s.startswith("units/"):
            return None, None
        readme = py_file.parent / "README.md"
        docs_s: str | None = None
        if readme.is_file():
            docs_s = str(readme.relative_to(repo)).replace("\\", "/")
        return rel_s, docs_s
    except Exception:
        return None, None


def _pipeline_docs_from_template(template_path: str | None) -> str | None:
    if not (template_path or "").strip():
        return None
    repo = _repo_root()
    wf = repo / template_path.strip()
    readme = wf.parent / "README.md"
    if readme.is_file():
        try:
            return str(readme.relative_to(repo)).replace("\\", "/")
        except ValueError:
            return None
    return None


def _library_read_file_paths(spec: object) -> tuple[str | None, str | None]:
    """Resolved source/docs paths for Units Library (explicit registry fields or inference)."""
    explicit_src = getattr(spec, "library_source_path", None)
    explicit_docs = getattr(spec, "library_docs_path", None)
    if explicit_src or explicit_docs:
        es = (str(explicit_src).strip() if explicit_src else None) or None
        ed = (str(explicit_docs).strip() if explicit_docs else None) or None
        return es, ed
    step_fn = getattr(spec, "step_fn", None)
    src, docs = _infer_library_paths_from_step_fn(step_fn)
    if getattr(spec, "pipeline", False) and getattr(spec, "template_path", None):
        tp = str(spec.template_path).strip()
        if tp:
            if src is None:
                src = tp.replace("\\", "/")
            if docs is None:
                docs = _pipeline_docs_from_template(tp)
    return src, docs


def _format_library_line(type_name: str, description: str, spec: object) -> str:
    base = f"{type_name} : {description}"
    src, docs = _library_read_file_paths(spec)
    if not src and not docs:
        return base
    parts: list[str] = []
    if src:
        parts.append(f"source={src}")
    if docs:
        parts.append(f"docs={docs}")
    return base + " — read_file: " + " ".join(parts)


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


def collect_source_paths_for_unit_types(type_names: list[str] | None) -> list[str]:
    """
    Unique ordered repo-relative paths (source then docs per type) for read_file / RAG.
    Used when read_code_block targets a unit with no graph code_block to load registry docs.
    """
    _ensure_units_registered_for_library()
    from units.registry import get_unit_spec

    order: list[str] = []
    seen: set[str] = set()
    for raw in type_names or []:
        t = (raw or "").strip()
        if not t:
            continue
        spec = get_unit_spec(t)
        if not spec:
            continue
        src, docs = _library_read_file_paths(spec)
        for p in (src, docs):
            if p and p not in seen:
                seen.add(p)
                order.append(p)
    return order


def format_units_library_for_prompt(
    graph_summary_dict: dict,
    *,
    implementation_links_for_types: list[str] | set[str] | frozenset[str] | None = None,
) -> str:
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
    - function / exec: code-block-driven units; omitted when ``coding_is_allowed`` is False in
      ``config/app_settings.json`` (aligned with prompt inject and ``add_code_block`` rejection).
    - PyFlow units (constant, branch, reroute, etc.): only shown when graph has environment "pyflow".
    - implementation_links_for_types: when set, only those registry type names get
      ``read_file: source=… docs=…`` suffixes; other lines stay type-only (saves prompt size).
      When empty/None, no implementation links on any line.
    """
    from core.graph.graph_edits import is_coding_allowed_from_app_settings
    from core.normalizer.runtime_detector import is_external_runtime
    from units.registry import UNIT_REGISTRY, get_unit_spec

    _ensure_units_registered_for_library()
    coding_allowed = is_coding_allowed_from_app_settings()

    if implementation_links_for_types is None:
        link_type_set: frozenset[str] = frozenset()
    elif isinstance(implementation_links_for_types, (set, frozenset)):
        link_type_set = frozenset(str(x).strip() for x in implementation_links_for_types if str(x).strip())
    else:
        link_type_set = frozenset(str(x).strip() for x in implementation_links_for_types if str(x).strip())

    def _line(type_name: str, desc: str, spec: object) -> str:
        if type_name in link_type_set:
            return _format_library_line(type_name, desc, spec)
        return f"{type_name} : {desc}"

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

        if not coding_allowed and type_name in ("function", "exec"):
            continue

        desc = spec.description or type_name
        if is_pipeline:
            pipeline_lines.append(_line(type_name, desc, spec))
        else:
            unit_lines.append(_line(type_name, desc, spec))

    # When coding is allowed, ensure "function" is listed if filters dropped it (env-agnostic).
    seen = {line.split(" : ")[0].strip() for line in unit_lines}
    if coding_allowed and "function" not in seen:
        spec = get_unit_spec("function")
        desc = (spec.description or "function") if spec else "function"
        unit_lines.append(_line("function", desc, spec) if spec else f"function : {desc}")

    try:
        from units.env_loaders import known_environment_tags
        known_envs = known_environment_tags()
    except Exception:
        known_envs = []
    graph_envs = sorted(env_set) if env_set else []

    if not unit_lines and not pipeline_lines and not known_envs:
        return ""

    parts = ["---", "Units Library available for this graph:", ""]
    if link_type_set:
        parts.append(
            "Implementation read_file paths (repo-relative) are shown only for the types indicated below; "
            "use action read_file with path set to each value."
        )
        parts.append("")
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
