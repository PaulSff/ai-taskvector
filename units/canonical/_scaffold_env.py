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


def patch_env_loaders_import(root: Path, env_tag: str) -> tuple[bool, str | None]:
    """Append try/import units.<tag> after the semantics block in units/env_loaders.py."""
    path = root / "units" / "env_loaders.py"
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as e:
        return False, str(e)
    if f"import units.{env_tag}" in text:
        return False, None
    anchor = """    try:
        import units.semantics  # noqa: F401  # registers "semantics" env loader
    except Exception:
        pass"""
    if anchor not in text:
        return False, "env_loaders.py: semantics import block anchor missing"
    block = f"""{anchor}
    try:
        import units.{env_tag}  # noqa: F401  # scaffolded by list_environment
    except Exception:
        pass"""
    text = text.replace(anchor, block, 1)
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
    except Exception as e:
        return False, f"import {mod_name}: {e}"
    fn = getattr(mod, fn_name, None)
    if not callable(fn):
        return False, f"{mod_name} missing callable {fn_name}"
    try:
        fn()
    except Exception as e:
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
    from units.env_loaders import known_environment_tags

    tag = normalize_env_tag(new_environment_id)
    if not tag:
        return {"ok": False, "error": "new_environment_id is required"}
    if tag in known_environment_tags():
        return {"ok": False, "error": f"environment {tag!r} already registered"}
    readme = str(readme_md) if readme_md is not None else ""

    env_pkg = (root / "units" / tag).resolve()
    root_units = (root / "units").resolve()
    if root_units not in env_pkg.parents:
        raise ValueError("path escapes units/")
    if env_pkg.exists():
        return {"ok": False, "error": f"units/{tag} already exists"}

    fn = f"register_{tag}_units"
    init_py = f'''"""Environment "{tag}" units (scaffolded by list_environment). See README.md."""\nfrom __future__ import annotations\n\nfrom units.registry import UNIT_REGISTRY\n\n\ndef {fn}() -> None:\n    """Register units for {tag}. Add register_* calls as you add units under units/{tag}/."""\n    pass\n\n\nfrom units.env_loaders import register_env_loader\n\nregister_env_loader("{tag}", {fn})\n\n__all__ = ["{fn}"]\n'''

    write_text(env_pkg / "README.md", readme)
    write_text(env_pkg / "__init__.py", init_py)

    changed, err = patch_env_loaders_import(root, tag)
    if err:
        shutil.rmtree(env_pkg, ignore_errors=True)
        return {"ok": False, "error": err}

    try:
        importlib.import_module(f"units.{tag}")
    except Exception as e:
        shutil.rmtree(env_pkg, ignore_errors=True)
        return {
            "ok": False,
            "error": f"import units.{tag}: {e}",
            "env_loaders_patched": changed,
        }

    return {
        "ok": True,
        "new_environment_id": tag,
        "folder": str(env_pkg.relative_to(root)),
        "env_loaders_patched": changed,
    }


def _unit_module_source(*, env_tag: str, snake: str, type_name: str) -> str:
    tn = type_name.replace("\\", "\\\\").replace('"', '\\"')
    return f'''"""Scaffolded unit {snake} (list_unit); logical type name "{tn}". Replace stub step with real logic."""
from __future__ import annotations

from typing import Any

from units.registry import UnitSpec, register_unit


def _step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    data = inputs.get("data")
    return ({{"data": data}}, state)


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
