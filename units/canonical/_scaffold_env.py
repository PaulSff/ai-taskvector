"""Shared helpers for list_unit / list_environment: paths, naming, and safe file writes."""
from __future__ import annotations

import importlib
import re
import shutil
import textwrap
from pathlib import Path
from typing import Any


def repo_root_containing_units(here: Path) -> Path:
    """Walk parents until a directory contains units/."""
    p = here.resolve()
    for parent in [p, *p.parents]:
        if (parent / "units").is_dir():
            return parent
    raise RuntimeError("could not locate repo root (no units/ directory)")


def normalize_env_tag(tag: str) -> str:
    t = str(tag).strip().lower().replace("-", "_")
    t = re.sub(r"[^a-z0-9_]", "", t)
    return t


def type_name_to_snake(type_name: str) -> str:
    """Folder/module name: PascalCase or kebab -> snake_case."""
    raw = str(type_name).strip()
    if not raw:
        return "new_unit"
    if "_" in raw and raw.lower() == raw and not re.search(r"[A-Z]", raw):
        s = re.sub(r"[^a-z0-9_]", "", raw.lower())
        return s or "new_unit"
    s1 = re.sub(r"[\s\-]+", "_", raw)
    s2 = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", "_", s1)
    s3 = re.sub(r"(?<=[A-Z])(?=[A-Z][a-z])", "_", s2)
    s4 = s3.replace("-", "_").lower()
    s5 = re.sub(r"[^a-z0-9_]", "", s4)
    return s5 or "new_unit"


def safe_under_units(root: Path, env_tag: str, *parts: str) -> Path:
    base = (root / "units" / env_tag).resolve()
    target = (base / Path(*parts)).resolve()
    if base != target and base not in target.parents:
        raise ValueError("path escapes units/<env>")
    return target


def write_text(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _read_text(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _try_write_text(path: Path, new_text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(new_text, encoding="utf-8")


def _env_enum_member_name(env_tag: str) -> str:
    """
    Enum member name convention: uppercase + non-alnum -> underscore, collapsed.
    Example: "my_env" -> "MY_ENV".
    """
    s = normalize_env_tag(env_tag).upper()
    s = re.sub(r"[^A-Z0-9_]", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s or "NEWENVIRONMENT"


def _env_class_name(env_tag: str) -> str:
    """
    Class name convention: TitleCase by splitting on underscores.
    Example: "my_env" -> "MyEnv".
    """
    parts = [p for p in normalize_env_tag(env_tag).split("_") if p]
    return "".join(p[:1].upper() + p[1:] for p in parts) or "Newenvironment"


def _insert_enum_member(process_graph_path: Path, env_tag: str) -> tuple[bool, str | None]:
    """
    Insert into EnvironmentType enum:
        <MEMBER> = "<env_tag>"
    """
    try:
        text = _read_text(process_graph_path)
    except OSError as e:
        return False, str(e)

    member = _env_enum_member_name(env_tag)
    target_line = f'{member} = "{env_tag}"'

    # Already present?
    if re.search(rf"^\s*{re.escape(member)}\s*=\s*{re.escape('\"' + env_tag + '\"')}\s*$", text, re.MULTILINE):
        return False, None
    if f'= "{env_tag}"' in text:
        return False, None

    # Insert near THERMODYNAMIC line (or first enum member)
    m = re.search(r'^\s*THERMODYNAMIC\s*=\s*"thermodynamic"\s*$', text, re.MULTILINE)
    if not m:
        return False, "process_graph.py: THERMODYNAMIC enum line missing"

    insert_at = m.end()
    insert = f'\n    {target_line}'
    new_text = text[:insert_at] + insert + text[insert_at:]

    try:
        _try_write_text(process_graph_path, new_text)
    except OSError as e:
        return False, str(e)

    return True, None


def _insert_normalizer_condition(normalizer_path: Path, env_tag: str) -> tuple[bool, str | None]:
    """
    Insert condition block after rag branch:
        elif "<env_tag>" in detected:
            env_type = EnvironmentType.<MEMBER>
    """
    try:
        text = _read_text(normalizer_path)
    except OSError as e:
        return False, str(e)

    member = _env_enum_member_name(env_tag)

    # Already present?
    if re.search(rf'elif\s+"{re.escape(env_tag)}"\s+in\s+detected\s*:\s*$', text, re.MULTILINE):
        return False, None
    if f"EnvironmentType.{member}" in text and f'"{env_tag}" in detected' in text:
        return False, None

    anchor = re.search(r'^\s*elif\s+"rag"\s+in\s+detected\s*:\s*$', text, re.MULTILINE)
    if not anchor:
        return False, "normalizer.py: rag branch anchor missing"

    # Find insertion point right after the env_type assignment under rag branch
    # We'll insert after the next non-empty line following the rag branch's assignment.
    # Simpler/brittle but localized: locate the rag assignment line and insert after it.
    rag_assign = re.search(
        r'^\s*elif\s+"rag"\s+in\s+detected\s*:\s*\n(?P<body>(?:^[ \t]*.*\n)+?)',
        text,
        re.MULTILINE,
    )
    # If we can't capture, fallback to inserting immediately after the rag line.
    if rag_assign:
        # insert after rag_assign match end
        insert_at = rag_assign.end()
    else:
        insert_at = anchor.end()

    insert_block = f'''
    elif "{env_tag}" in detected:
        env_type = EnvironmentType.{member}
'''
    new_text = text[:insert_at] + insert_block + text[insert_at:]

    try:
        _try_write_text(normalizer_path, new_text)
    except OSError as e:
        return False, str(e)

    return True, None


def _insert_factory_branch(factory_path: Path, env_tag: str) -> tuple[bool, str | None]:
    """
    Insert after the RAG branch's GraphEnv(...) return block, by anchoring on the
    **kwargs, line within that branch and inserting immediately after the closing
    `)`/`return` statement.
    """
    try:
        text = _read_text(factory_path)
    except OSError as e:
        return False, str(e)

    member = _env_enum_member_name(env_tag)
    class_name = _env_class_name(env_tag)

    # Already present?
    if f"EnvironmentType.{member}" in text and f"environments.native.{env_tag}" in text:
        return False, None

    # Anchor the start of the RAG branch
    rag_anchor = re.search(
        r'^\s*if\s+process_graph\.environment_type\s*==\s*EnvironmentType\.RAG\s*:\s*$',
        text,
        re.MULTILINE,
    )
    if not rag_anchor:
        return False, "factory.py: RAG branch anchor missing"

    # Work only inside the RAG branch region until the next top-level `if process_graph.environment_type == ...`
    # (same indentation style).
    # We'll take a conservative slice: from rag_anchor.end() until the next line that starts an `if process_graph.environment_type`
    # at the same indentation level (often 4 spaces).
    after_rag = text[rag_anchor.end():]

    # Find next sibling branch at same indentation: "if process_graph.environment_type == EnvironmentType.X:"
    next_if = re.search(
        r'^\s*if\s+process_graph\.environment_type\s*==\s*EnvironmentType\.\w+\s*:\s*$',
        after_rag,
        re.MULTILINE,
    )

    rag_block = after_rag if not next_if else after_rag[: next_if.start()]

    # Now find where the RAG GraphEnv call ends, anchored on the **kwargs line.
    # We locate the **kwargs line and then find the next line containing the closing `)` of GraphEnv call.
    # This assumes formatting:
    #   **kwargs,
    # )
    # or at least that `**kwargs,` appears just before the closing paren.
    kwargs_line = re.search(r'^\s*\*\*kwargs,\s*$', rag_block, re.MULTILINE)
    if not kwargs_line:
        return False, "factory.py: could not find '**kwargs,' line inside RAG branch"

    # Insert after the end of the GraphEnv(...) return statement.
    # Find the next line that starts with ')' (possibly with spaces) after the **kwargs line.
    close_paren = re.search(
        r'^\s*\)\s*$',
        rag_block[kwargs_line.end():],
        re.MULTILINE,
    )
    if close_paren:
        insert_at_local = kwargs_line.end() + close_paren.end()
    else:
        # Fallback: insert right after kwargs_line end (better than putting in the wrong place)
        insert_at_local = kwargs_line.end()

    # Compute absolute insert position in original `text`
    insert_at = rag_anchor.end() + insert_at_local

    branch = f'''
    if process_graph.environment_type == EnvironmentType.{member}:
            from environments.graph_env import GraphEnv
            from environments.native.{env_tag} import {class_name}EnvironmentSpec

            spec = {class_name}EnvironmentSpec()
            return GraphEnv(
                process_graph,
                goal,
                spec,
                dt=kwargs.get("dt", 0.1),
                max_steps=max_steps,
                rewards_config=rewards,
                render_mode=render_mode,
                randomize_params=randomize_params,
                **kwargs,
            )
'''

    # Insert and write
    new_text = text[:insert_at] + branch + text[insert_at:]
    try:
        _try_write_text(factory_path, new_text)
    except OSError as e:
        return False, str(e)

    return True, None


def patch_env_loaders_import(root: Path, env_tag: str) -> tuple[bool, str | None]:
    """Insert _import_optional('units.<tag>') into units/env_loaders.py after the semantics line."""
    path = root / "units" / "env_loaders.py"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return False, str(e)

    # Already present?
    if f'_import_optional("units.{env_tag}")' in text or f'import units.{env_tag}' in text:
        return False, None

    # Anchor on your existing semantics registration line
    sem_line = '    _import_optional("units.semantics")  # registers "semantics" env loader'
    if sem_line not in text:
        return False, "env_loaders.py: semantics optional line missing"

    insert_line = f'    _import_optional("units.{env_tag}")  # registers "{env_tag}" env loader'
    text = text.replace(sem_line, sem_line + "\n" + insert_line, 1)

    try:
        path.write_text(text, encoding="utf-8")
    except OSError as e:
        return False, str(e)

    return True, None


def patch_env_package_for_new_unit(root: Path, env_tag: str, snake: str) -> tuple[bool, str | None]:
    """
    Add import + register_*() call to units/<env>/__init__.py when safe (heuristic).
    Returns (changed, error_message).
    """
    init_path = root / "units" / env_tag / "__init__.py"
    if not init_path.is_file():
        return False, f"missing {init_path}"
    text = init_path.read_text(encoding="utf-8")
    import_line = f"from units.{env_tag}.{snake} import register_{snake}\n"
    if import_line in text:
        return False, None
    call_line = f"    register_{snake}()\n"
    if call_line in text:
        return False, None

    if "from units.env_loaders import register_env_loader" not in text:
        return False, None

    insert_at = text.find("from units.env_loaders import register_env_loader")
    text = text[:insert_at] + import_line + "\n" + text[insert_at:]

    fn_match = re.search(r"^def (register_\w+_units)\(\)[^:]*:", text, re.MULTILINE)
    if not fn_match:
        return False, f"no register_*_units() in units/{env_tag}/__init__.py"
    start = fn_match.end()
    body_start = text.find("\n", start)
    if body_start < 0:
        return False, "parse error: function body"
    slice_from_body = text[body_start + 1 :]
    next_def = re.search(r"^def \w", slice_from_body, re.MULTILINE)
    body_end_rel = next_def.start() if next_def else len(slice_from_body)
    body_only = slice_from_body[:body_end_rel]
    m_first_reg = re.search(r"^    register_\w+\(\)\s*$", body_only, re.MULTILINE)
    if m_first_reg:
        insert_body = body_start + 1 + m_first_reg.start()
    else:
        m_pass = re.search(r"^    pass\s*$", body_only, re.MULTILINE)
        if m_pass:
            insert_body = body_start + 1 + m_pass.start()
        else:
            insert_body = body_start + 1
    text = text[:insert_body] + call_line + text[insert_body:]
    init_path.write_text(text, encoding="utf-8")
    return True, None


def import_and_register_unit(env_tag: str, snake: str) -> tuple[bool, str | None]:
    """Import units.<env>.<snake>.<snake> and call register_<snake>()."""
    mod_name = f"units.{env_tag}.{snake}.{snake}"
    fn_name = f"register_{snake}"

    try:
        mod = importlib.import_module(mod_name)
    except ModuleNotFoundError as e:
        return False, f"import {mod_name}: {e}"
    except ImportError as e:
        return False, f"import {mod_name}: {e}"
    except (ValueError, RuntimeError) as e:
        return False, f"import {mod_name} unexpected error: {e}"

    fn = getattr(mod, fn_name, None)
    if fn is None or not callable(fn):
        return False, f"{mod_name} missing callable {fn_name}"

    try:
        fn()
    except (TypeError, ValueError, RuntimeError) as e:
        return False, f"{fn_name}(): {e}"

    return True, None


def _is_full_register_module_source(source: str, snake: str) -> bool:
    """True if source defines register_<snake> (full module written verbatim)."""
    return bool(re.search(rf"^\s*def\s+register_{re.escape(snake)}\s*\(", source, re.MULTILINE))


def _module_py_from_graph_source(
    *,
    env_tag: str,
    snake: str,
    type_name: str,
    source: str,
) -> str:
    """
    Build <snake>.py either from a full module (defines register_<snake>) or by wrapping
    graph code_block source as the body of _step(...).
    """
    raw = (source or "").strip("\n")
    if _is_full_register_module_source(raw, snake):
        return raw if raw.endswith("\n") else raw + "\n"
    tn = type_name.replace("\\", "\\\\").replace('"', '\\"')
    body = textwrap.indent(raw.rstrip() + "\n", "    ")
    return f'''"""Scaffolded unit {snake} (list_unit); logical type name "{tn}". Code from graph code_block."""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit


def _step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
{body}


def register_{snake}() -> None:
    register_unit(UnitSpec(
        type_name="{tn}",
        input_ports=[("data", "Any")],
        output_ports=[("data", "Any")],
        step_fn=_step,
        environment_tags=["{env_tag}"],
        description="Scaffolded unit; see README.md under units/{env_tag}/{snake}/.",
    ))
'''


def run_list_unit(
    root: Path,
    environment: str,
    new_unit_type: str,
    readme_md: str,
    module_source: str | None = None,
) -> dict[str, Any]:
    from units.env_loaders import known_environment_tags

    env_tag = normalize_env_tag(environment)
    if env_tag not in known_environment_tags():
        return {
            "ok": False,
            "error": f"unknown environment {environment!r}; known: {known_environment_tags()}",
        }
    type_name = str(new_unit_type).strip()
    if not type_name:
        return {"ok": False, "error": "new_unit_type is required"}
    snake = type_name_to_snake(type_name)
    readme = str(readme_md) if readme_md is not None else ""

    unit_dir = safe_under_units(root, env_tag, snake)
    if unit_dir.exists() and any(unit_dir.iterdir()):
        return {"ok": False, "error": f"target already exists and is non-empty: {unit_dir}"}

    if module_source is None:
        return {"ok": False, "error": "module_source is required (from graph code_block by code_block_id)"}
    ms = str(module_source)
    if not ms.strip():
        return {"ok": False, "error": "code_block source is empty"}
    py = _module_py_from_graph_source(env_tag=env_tag, snake=snake, type_name=type_name, source=ms)
    init_py = f'"""{snake} unit package. See README.md."""\nfrom units.{env_tag}.{snake}.{snake} import register_{snake}\n\n__all__ = ["register_{snake}"]\n'

    write_text(unit_dir / "README.md", readme)
    write_text(unit_dir / "__init__.py", init_py)
    write_text(unit_dir / f"{snake}.py", py)

    ok_reg, reg_err = import_and_register_unit(env_tag, snake)
    patched_init = False
    patch_err: str | None = None
    if ok_reg:
        patched_init, patch_err = patch_env_package_for_new_unit(root, env_tag, snake)
    if not ok_reg:
        shutil.rmtree(unit_dir, ignore_errors=True)
    return {
        "ok": ok_reg,
        "environment": env_tag,
        "new_unit_type": type_name,
        "folder": str(unit_dir.relative_to(root)) if ok_reg else None,
        "patched_env_init": patched_init,
        "patch_error": patch_err,
        "register_error": None if ok_reg else reg_err,
    }


def run_list_environment(root: Path, new_environment_id: str, readme_md: str) -> dict[str, Any]:
    """
    Create a new environment package and wire it through core:
      1) core/schemas/process_graph.py: EnvironmentType enum member
      2) core/normalizer/normalizer.py: normalizer condition for detected environments
      3) core/env_factory/factory.py: env factory branch returning GraphEnv with the native spec
      4) environments/native/<newenvironment>: clone from environments/native/network and rename internals

    Also creates units/<env_tag>/ package and patches units/env_loaders.py as in the original behavior.
    """
    from units.env_loaders import known_environment_tags

    env_tag = normalize_env_tag(new_environment_id)
    if not env_tag:
        return {"ok": False, "error": "new_environment_id is required"}
    if env_tag in known_environment_tags():
        return {"ok": False, "error": f"environment {env_tag!r} already registered"}

    readme = str(readme_md) if readme_md is not None else ""

    # ---- Step 1/2/3: core wiring (ENUM, NORMALIZER, FACTORY) ----
    process_graph_path = root / "core" / "schemas" / "process_graph.py"
    normalizer_path = root / "core" / "normalizer" / "normalizer.py"
    factory_path = root / "core" / "env_factory" / "factory.py"

    enum_changed, enum_err = _insert_enum_member(process_graph_path, env_tag)
    if enum_err:
        return {"ok": False, "error": enum_err, "phase": "core.schemas.process_graph"}

    norm_changed, norm_err = _insert_normalizer_condition(normalizer_path, env_tag)
    if norm_err:
        return {"ok": False, "error": norm_err, "phase": "core.normalizer.normalizer"}

    factory_changed, factory_err = _insert_factory_branch(factory_path, env_tag)
    if factory_err:
        return {"ok": False, "error": factory_err, "phase": "core.env_factory.factory"}

    # ---- Step 4: clone native env package from network ----
    src_native = root / "environments" / "native" / "network"
    dst_native = root / "environments" / "native" / env_tag

    if dst_native.exists():
        return {"ok": False, "error": f"native environment already exists: {dst_native}"}
    if not src_native.is_dir():
        return {"ok": False, "error": f"template environment missing: {src_native}"}

    shutil.copytree(src_native, dst_native)

    class_name = _env_class_name(env_tag)
    loader_new_fn = f"load_{env_tag}_env"

    # 4a spec.py rename
    spec_path = dst_native / "spec.py"
    try:
        spec_text = _read_text(spec_path)
    except OSError as e:
        return {"ok": False, "error": f"spec.py read: {e}"}

    # Update import line
    spec_text = re.sub(
        r"from units\.network import register_network_units",
        f"from units.{env_tag} import register_{env_tag}_units",
        spec_text,
    )

    # Update class name and docstring + register call
    spec_text = re.sub(r"class\s+NetworkEnvironmentSpec\s*:", f"class {class_name}EnvironmentSpec:", spec_text)
    spec_text = spec_text.replace(
        '"""EnvironmentSpec for network workflows. Step-based; no physical state."""',
        f'"""{class_name}EnvironmentSpec for {env_tag} workflows. Step-based; no physical state."""',
    )
    spec_text = re.sub(r"register_network_units\(\)", f"register_{env_tag}_units()", spec_text)
    spec_text = re.sub(r'Optional network units not available', f'Optional {env_tag} units not available', spec_text)

    try:
        _try_write_text(spec_path, spec_text)
    except OSError as e:
        return {"ok": False, "error": f"spec.py write: {e}"}

    # 4b loader.py function rename
    loader_path = dst_native / "loader.py"
    try:
        loader_text = _read_text(loader_path)
    except OSError as e:
        return {"ok": False, "error": f"loader.py read: {e}"}

    # Locate old function name and rename it
    loader_text = re.sub(r"def\s+load_network_env\s*\(", f"def {loader_new_fn}(", loader_text)
    try:
        _try_write_text(loader_path, loader_text)
    except OSError as e:
        return {"ok": False, "error": f"loader.py write: {e}"}

    # 4c __init__.py rename header + exports
    init_path = dst_native / "__init__.py"
    try:
        init_text = _read_text(init_path)
    except OSError as e:
        return {"ok": False, "error": f"__init__.py read: {e}"}

    init_text = re.sub(r'"""Network native environment"""', f'"""{class_name} native environment"""', init_text)
    init_text = re.sub(
        r"from environments\.native\.network\.loader import load_network_env",
        f"from environments.native.{env_tag}.loader import {loader_new_fn}",
        init_text,
    )
    init_text = re.sub(
        r"from environments\.native\.network\.spec import NetworkEnvironmentSpec",
        f"from environments.native.{env_tag}.spec import {class_name}EnvironmentSpec",
        init_text,
    )
    init_text = re.sub(
        r'__all__\s*=\s*\[\s*"NetworkEnvironmentSpec"\s*,\s*"load_network_env"\s*\]',
        f'__all__ = ["{class_name}EnvironmentSpec", "{loader_new_fn}"]',
        init_text,
    )

    # If repo template __all__ differs slightly, ensure at least the loader/spec exports exist.
    if f"{class_name}EnvironmentSpec" not in init_text or loader_new_fn not in init_text:
        init_text = f'''"""{class_name} native environment"""

from environments.native.{env_tag}.loader import {loader_new_fn}
from environments.native.{env_tag}.spec import {class_name}EnvironmentSpec

__all__ = ["{class_name}EnvironmentSpec", "{loader_new_fn}"]
'''

    try:
        _try_write_text(init_path, init_text)
    except OSError as e:
        return {"ok": False, "error": f"__init__.py write: {e}"}

    # ---- Units package creation + units/env_loaders patch (kept from original behavior) ----
    env_pkg = (root / "units" / env_tag).resolve()
    root_units = (root / "units").resolve()
    if root_units not in env_pkg.parents:
        raise ValueError("path escapes units/")
    if env_pkg.exists():
        shutil.rmtree(dst_native, ignore_errors=True)
        return {"ok": False, "error": f"units/{env_tag} already exists"}

    fn = f"register_{env_tag}_units"
    init_py = f'''"""Environment "{env_tag}" units (scaffolded by list_environment). See README.md."""
from __future__ import annotations

from units.registry import UNIT_REGISTRY


def {fn}() -> None:
    """Register units for {env_tag}. Add register_* calls as you add units under units/{env_tag}/."""
    pass


from units.env_loaders import register_env_loader

register_env_loader("{env_tag}", {fn})

__all__ = ["{fn}"]
'''

    write_text(env_pkg / "README.md", readme)
    write_text(env_pkg / "__init__.py", init_py)

    changed, err = patch_env_loaders_import(root, env_tag)
    if err:
        shutil.rmtree(env_pkg, ignore_errors=True)
        shutil.rmtree(dst_native, ignore_errors=True)
        return {"ok": False, "error": err}

    try:
        importlib.import_module(f"units.{env_tag}")
    except ImportError as e:
        shutil.rmtree(env_pkg, ignore_errors=True)
        shutil.rmtree(dst_native, ignore_errors=True)
        return {
            "ok": False,
            "error": f"import units.{env_tag}: {e}",
            "env_loaders_patched": changed,
        }

    return {
        "ok": True,
        "new_environment_id": env_tag,
        "core_enum_changed": enum_changed,
        "core_normalizer_changed": norm_changed,
        "core_factory_changed": factory_changed,
        "native_env_folder": str(dst_native.relative_to(root)),
        "units_folder": str(env_pkg.relative_to(root)),
        "env_loaders_patched": changed,
    }
