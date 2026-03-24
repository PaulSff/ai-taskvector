"""
CleanText unit: preprocess user text for robust language detection.

Pipeline:
1) Parse markdown and remove code tokens (fenced/indented/inline).
2) Drop code/noise-like blocks (JSON/log/symbol-heavy).
3) Normalize whitespace and return compact natural-language text.

Primary output is `text` for wiring into LanguageDetector.
"""
from __future__ import annotations

import re
from typing import Any

from units.registry import UnitSpec, register_unit

_DEFAULT_SYMBOL_DENSITY_THRESHOLD = 0.25
_DEFAULT_MIN_BLOCK_LEN = 4
_DEFAULT_MAX_CHARS = 600

_CODE_LIKE_CHARS = set("{}[]();=<>:+-*/\\%$@#'\"`|,.")
_URL_LINE_RE = re.compile(r"(\s*(https?://|www\.)\S+\s*)+$", re.IGNORECASE)
_BRACKETS_ONLY_RE = re.compile(r"[\[\]\{\}\(\),:\"']+")
_CONSOLE_PREFIX_RE = re.compile(r"^\s*(>|\$|#)\s*", re.MULTILINE)
_CONSOLE_LOG_RE = re.compile(r"^(>|\$|#|\buser\b:|\d{2}:\d{2}:\d{2}|>>>|\.\.\.)", re.IGNORECASE)
_JSON_KEY_RE = re.compile(r'^\s*"[^"]+"\s*:\s*')
_JSON_BRACE_LINE_RE = re.compile(r"^\s*[\{\}\[\],]+\s*$")


def _normalize_text(raw: Any) -> str:
    if raw is None:
        return ""
    if isinstance(raw, bytes):
        try:
            return raw.decode("utf-8", errors="replace")
        except Exception:
            return ""
    return str(raw)


def _is_symbol_heavy(block: str, threshold: float) -> bool:
    if not block.strip():
        return False
    s = sum(1 for c in block if c in _CODE_LIKE_CHARS)
    return (s / max(1, len(block))) >= threshold


def _looks_like_console_log(block: str) -> bool:
    first = block.strip().splitlines()[0] if block.strip() else ""
    return bool(_CONSOLE_LOG_RE.match(first))


def _is_code_by_pygments(block: str) -> bool:
    try:
        from pygments.lexers import guess_lexer
        from pygments.util import ClassNotFound
    except Exception:
        return False
    try:
        lexer = guess_lexer(block)
        name = lexer.name.lower()
        return any(
            k in name
            for k in (
                "python",
                "javascript",
                "java",
                "c++",
                "c#",
                "json",
                "xml",
                "html",
                "yaml",
                "bash",
                "sh",
                "php",
                "ruby",
                "go",
                "rust",
                "sql",
            )
        )
    except Exception:
        return False


def _block_is_code(block: str, symbol_density_threshold: float) -> bool:
    if len(block) < 30:
        return _is_symbol_heavy(block, symbol_density_threshold) or _looks_like_console_log(block)
    if _is_symbol_heavy(block, symbol_density_threshold) or _looks_like_console_log(block):
        return True
    return _is_code_by_pygments(block)


def _line_is_json_noise(line: str) -> bool:
    s = line.strip()
    if not s:
        return False
    if _JSON_BRACE_LINE_RE.fullmatch(s):
        return True
    if _JSON_KEY_RE.match(s):
        return True
    # Typical JSON primitive/value tails
    if s in ("true", "false", "null") or s.endswith(","):
        if ":" in s or s.startswith('"') or s.startswith("{") or s.startswith("["):
            return True
    return False


def _strip_code_markdown(md_text: str) -> str:
    try:
        from markdown_it import MarkdownIt
    except Exception:
        return md_text
    md = MarkdownIt()
    tokens = md.parse(md_text)
    parts: list[str] = []
    for t in tokens:
        if t.type in ("fence", "code_block"):
            continue
        if t.type == "inline":
            inline_buf: list[str] = []
            for child in t.children or []:
                if child.type == "code_inline":
                    continue
                if child.type == "text":
                    inline_buf.append(child.content)
                elif child.type in ("softbreak", "hardbreak"):
                    inline_buf.append("\n")
                else:
                    inline_buf.append(getattr(child, "content", "") or "")
            parts.append("".join(inline_buf))
        elif t.type.endswith("_close"):
            parts.append("\n\n")
    return "".join(parts)


def _clean_text(
    text: str,
    *,
    symbol_density_threshold: float,
    min_block_len: int,
    max_chars: int,
) -> str:
    cleaned = _strip_code_markdown(text)
    blocks = [b for b in re.split(r"\n{2,}", cleaned)]
    kept: list[str] = []
    for b in blocks:
        s = b.strip()
        if not s:
            continue
        if _BRACKETS_ONLY_RE.fullmatch(s):
            continue
        if _URL_LINE_RE.fullmatch(s):
            continue
        if len(s) < min_block_len:
            continue
        if _block_is_code(s, symbol_density_threshold):
            continue
        # Remove JSON-ish lines inside mixed paragraphs, keep natural-language lines.
        filtered_lines = [ln for ln in s.splitlines() if not _line_is_json_noise(ln)]
        s = "\n".join(filtered_lines).strip()
        if not s:
            continue
        s = re.sub(r"^[\{\[\(]+", "", s)
        s = re.sub(r"[\}\]\)]+$", "", s)
        s = _CONSOLE_PREFIX_RE.sub("", s)
        s = re.sub(r"\s{2,}", " ", s).strip()
        if s:
            kept.append(s)
    out = "\n\n".join(kept).strip()
    if max_chars > 0 and len(out) > max_chars:
        out = out[:max_chars].rstrip()
    return out


def _clean_text_step(
    params: dict[str, Any],
    inputs: dict[str, Any],
    state: dict[str, Any],
    dt: float,
) -> tuple[dict[str, Any], dict[str, Any]]:
    raw = _normalize_text((inputs or {}).get("text"))
    if not raw:
        raw = _normalize_text((params or {}).get("text"))
    p = params or {}
    try:
        symbol_density_threshold = float(p.get("symbol_density_threshold", _DEFAULT_SYMBOL_DENSITY_THRESHOLD))
    except Exception:
        symbol_density_threshold = _DEFAULT_SYMBOL_DENSITY_THRESHOLD
    symbol_density_threshold = max(0.0, min(1.0, symbol_density_threshold))
    try:
        min_block_len = int(p.get("min_block_len", _DEFAULT_MIN_BLOCK_LEN))
    except Exception:
        min_block_len = _DEFAULT_MIN_BLOCK_LEN
    min_block_len = max(1, min_block_len)
    try:
        max_chars = int(p.get("max_chars", _DEFAULT_MAX_CHARS))
    except Exception:
        max_chars = _DEFAULT_MAX_CHARS
    max_chars = max(0, max_chars)
    try:
        out = _clean_text(
            raw,
            symbol_density_threshold=symbol_density_threshold,
            min_block_len=min_block_len,
            max_chars=max_chars,
        )
        return ({"text": out, "error": None}, state)
    except Exception as e:  # noqa: BLE001
        return ({"text": raw, "error": str(e)[:300] or "clean_text failed"}, state)


def register_clean_text() -> None:
    register_unit(
        UnitSpec(
            type_name="CleanText",
            input_ports=[("text", "str")],
            output_ports=[("text", "str"), ("error", "str")],
            step_fn=_clean_text_step,
            environment_tags=["semantics"],
            environment_tags_are_agnostic=False,
            runtime_scope=None,
            description=(
                "Cleans markdown/code/JSON-like noise from text before language detection. "
                "Outputs cleaned text and optional error."
            ),
        )
    )


__all__ = ["register_clean_text"]
