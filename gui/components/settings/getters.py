"""Read-side accessors for app settings, paths, RAG, and LLM config."""
from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from .constants import (
    DEFAULT_CREATE_FILENAME_WORKFLOW_PATH,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_PROJECT_NAME,
    DEFAULT_READ_FILE_RAG_MAX_CHARS,
    DEFAULT_READ_FILE_RAG_SNIPPET_MAX,
    DEFAULT_RL_COACH_PROMPT_PATH,
    DEFAULT_TRAINING_CONFIG_PATH,
    DEFAULT_WD_LLM_NUM_PREDICT,
    DEFAULT_WD_LLM_TEMPERATURE,
    DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH,
    DEFAULT_WORKFLOW_DESIGNER_RAG_TOP_K,
    DEFAULT_WORKFLOWS_DIR,
    DEFAULT_WORKFLOW_SAVE_PATH_TEMPLATE,
    DEFAULT_RAG_FORMAT_MAX_CHARS,
    DEFAULT_RAG_FORMAT_SNIPPET_MAX,
    DEFAULT_RAG_MIN_SCORE,
    DEFAULT_RAG_TOP_K,
    KEY_OLLAMA_API_KEY,
    KEY_OLLAMA_HOST,
    KEY_OLLAMA_MODEL,
    KEY_WORKFLOW_UNDO_MAX_DEPTH,
    KEY_CHAT_STREAM_UI_INTERVAL_MS,
    DEFAULT_WORKFLOW_UNDO_MAX_DEPTH,
    DEFAULT_CHAT_STREAM_UI_INTERVAL_MS,
    MIN_WORKFLOW_UNDO_MAX_DEPTH,
    MAX_WORKFLOW_UNDO_MAX_DEPTH,
    MIN_CHAT_STREAM_UI_INTERVAL_MS,
    MAX_CHAT_STREAM_UI_INTERVAL_MS,
    MIN_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
    MAX_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
    DEFAULT_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
    DEFAULT_AUTO_DELEGATION_IS_ALLOWED,
    KEY_AUTO_DELEGATION_IS_ALLOWED,
    KEY_CODING_IS_ALLOWED,
    KEY_CONTRIBUTION_IS_ALLOWED,
    DEFAULT_CODING_IS_ALLOWED,
    DEFAULT_CONTRIBUTION_IS_ALLOWED,
    DEFAULT_CHAT_HISTORY_DIR,
    DEFAULT_MYDATA_DIR,
    KEY_BEST_MODEL_PATH,
    KEY_CHAT_HISTORY_DIR,
    KEY_MYDATA_DIR,
    KEY_TRAINING_CONFIG_PATH,
    KEY_WORKFLOW_PROJECT_NAME,
    KEY_WORKFLOW_SAVE_PATH_TEMPLATE,
    KEY_WINDOW_WIDTH,
    KEY_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    DEFAULT_WINDOW_HEIGHT,
    KEY_DEBUG_LOG_PATH,
    DEFAULT_DEBUG_LOG_PATH,
    KEY_CREATE_FILENAME_PROMPT_PATH,
    KEY_CREATE_FILENAME_WORKFLOW_PATH,
    KEY_WORKFLOW_DESIGNER_PROMPT_PATH,
    KEY_RL_COACH_PROMPT_PATH,
    DEFAULT_CREATE_FILENAME_PROMPT_PATH,
)
from .paths import REPO_ROOT, _resolve_dir, _resolve_workflow_path
from .persistence import load_settings
from .role_yaml import _role_llm_float, _role_llm_int, _role_llm_str


def _default_ollama_host() -> str:
    """Default Ollama host; use OLLAMA_HOST env in Docker (e.g. http://ollama:11434)."""
    return (os.environ.get("OLLAMA_HOST") or "").strip() or DEFAULT_OLLAMA_HOST


def _default_ollama_model() -> str:
    """Default Ollama model; use OLLAMA_MODEL env to override."""
    return (os.environ.get("OLLAMA_MODEL") or "").strip() or DEFAULT_OLLAMA_MODEL


def _default_chat_history_dir() -> str:
    return DEFAULT_CHAT_HISTORY_DIR


def _default_project_name() -> str:
    return DEFAULT_PROJECT_NAME


def _default_workflow_save_path_template() -> str:
    return DEFAULT_WORKFLOW_SAVE_PATH_TEMPLATE


def get_workflow_project_name() -> str:
    """Return the stored workflow project name (default if not set)."""
    return load_settings().get(KEY_WORKFLOW_PROJECT_NAME) or _default_project_name()


def get_workflow_save_path_template() -> str:
    """Return the stored workflow save path template (default if not set)."""
    return load_settings().get(KEY_WORKFLOW_SAVE_PATH_TEMPLATE) or _default_workflow_save_path_template()


def get_training_config_path() -> str:
    """Return the last-used training config path from settings (or default). Used by Training tab."""
    return load_settings().get(KEY_TRAINING_CONFIG_PATH) or DEFAULT_TRAINING_CONFIG_PATH


def get_best_model_path() -> str:
    """Return the best model path from settings (directory or file path). Updated when training completes."""
    return (load_settings().get(KEY_BEST_MODEL_PATH) or "").strip()


def get_window_width() -> int:
    """Return the last-used window width (or default ~30% larger than 1200). Used at startup."""
    try:
        return int(load_settings().get(KEY_WINDOW_WIDTH) or DEFAULT_WINDOW_WIDTH)
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_WIDTH


def get_window_height() -> int:
    """Return the last-used window height (or default ~30% larger than 800). Used at startup."""
    try:
        return int(load_settings().get(KEY_WINDOW_HEIGHT) or DEFAULT_WINDOW_HEIGHT)
    except (TypeError, ValueError):
        return DEFAULT_WINDOW_HEIGHT


def get_workflow_save_dir() -> Path:
    """Return the directory where workflows are saved (from template + project name). Used to find latest workflow on startup."""
    template = get_workflow_save_path_template() or _default_workflow_save_path_template()
    proj = get_workflow_project_name() or _default_project_name()
    resolved = (template or "").replace("$PROJECT_NAME$", proj).replace("$YY-MM-DD-HHMMSS$", "").strip()
    if not resolved:
        return REPO_ROOT / DEFAULT_WORKFLOWS_DIR / _default_project_name()
    p = Path(resolved).expanduser()
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p.parent


def get_rag_context_workflow_path() -> Path:
    """
    Return the path to the RAG context workflow (RagSearch → Filter → FormatRagPrompt).

    Source of truth: ``assistants/tools/rag_search/tool.yaml`` key ``workflow`` (see
    ``assistants.tools.workflow_path.get_tool_workflow_path``).
    """
    from assistants.tools.workflow_path import get_tool_workflow_path

    return get_tool_workflow_path("rag_search")


def get_rag_update_workflow_path() -> Path:
    """Return the path to the RAG index update workflow from ``rag/ragconf.yaml`` ``rag_update_workflow_path``."""
    from rag.ragconf_loader import DEFAULT_RAG_UPDATE_WORKFLOW_PATH, rag_update_workflow_path_raw

    raw = rag_update_workflow_path_raw()
    return _resolve_workflow_path(raw, DEFAULT_RAG_UPDATE_WORKFLOW_PATH)


def get_doc_to_text_workflow_path() -> Path:
    """Return the path to the doc-to-text workflow from ``rag/ragconf.yaml`` ``doc_to_text_workflow_path``."""
    from rag.ragconf_loader import DEFAULT_DOC_TO_TEXT_WORKFLOW_PATH, doc_to_text_workflow_path_raw

    raw = doc_to_text_workflow_path_raw()
    return _resolve_workflow_path(raw, DEFAULT_DOC_TO_TEXT_WORKFLOW_PATH)


def get_mydata_file_manager_refresh_workflow_path() -> Path:
    """Return the mydata file-manager refresh workflow from ``rag/ragconf.yaml``."""
    from rag.ragconf_loader import (
        DEFAULT_MYDATA_FILE_MANAGER_REFRESH_WORKFLOW_PATH,
        mydata_file_manager_refresh_workflow_path_raw,
    )

    raw = mydata_file_manager_refresh_workflow_path_raw()
    return _resolve_workflow_path(raw, DEFAULT_MYDATA_FILE_MANAGER_REFRESH_WORKFLOW_PATH)


def get_mydata_storage_report_only_workflow_path() -> Path:
    """Report-only mydata browser workflow (no MydataOrganize); from ``rag/ragconf.yaml``."""
    from rag.ragconf_loader import (
        DEFAULT_MYDATA_STORAGE_REPORT_ONLY_WORKFLOW_PATH,
        mydata_storage_report_only_workflow_path_raw,
    )

    raw = mydata_storage_report_only_workflow_path_raw()
    return _resolve_workflow_path(raw, DEFAULT_MYDATA_STORAGE_REPORT_ONLY_WORKFLOW_PATH)


def get_workflow_designer_prompt_path() -> Path:
    """Return the path to the Workflow Designer prompt template (from app settings)."""
    raw = load_settings().get(KEY_WORKFLOW_DESIGNER_PROMPT_PATH) or DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH
    return _resolve_workflow_path(raw, DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH)


def get_rl_coach_prompt_path() -> Path:
    """Return the path to the RL Coach prompt template (from app settings)."""
    raw = load_settings().get(KEY_RL_COACH_PROMPT_PATH) or DEFAULT_RL_COACH_PROMPT_PATH
    return _resolve_workflow_path(raw, DEFAULT_RL_COACH_PROMPT_PATH)


def get_create_filename_workflow_path() -> Path:
    """
    Return the path to the create_filename workflow JSON.

    Default: ``assistants.roles.workflow_path.get_role_chat_workflow_path("chat_name_creator")``
    (``chat.workflow`` in ``assistants/roles/chat_name_creator/role.yaml``).

    If ``create_filename_workflow_path`` is set in app settings to a non-empty path, that value wins
    (for deployments that keep a custom file outside the role folder). Legacy value
    ``assistants/create_filename.json`` is ignored so the role path is used.
    """
    raw = load_settings().get(KEY_CREATE_FILENAME_WORKFLOW_PATH)
    raw = (raw if isinstance(raw, str) else "").strip()
    norm = raw.replace("\\", "/")
    if norm == "assistants/create_filename.json":
        raw = ""
    if raw:
        return _resolve_workflow_path(raw, DEFAULT_CREATE_FILENAME_WORKFLOW_PATH)
    from assistants.roles.workflow_path import get_role_chat_workflow_path

    return get_role_chat_workflow_path("chat_name_creator")


def get_create_filename_prompt_path() -> Path:
    """Return the path to the create_filename prompt template (from app settings)."""
    raw = load_settings().get(KEY_CREATE_FILENAME_PROMPT_PATH) or DEFAULT_CREATE_FILENAME_PROMPT_PATH
    return _resolve_workflow_path(raw, DEFAULT_CREATE_FILENAME_PROMPT_PATH)


def get_debug_log_path() -> Path:
    """Return the path to the debug log file (e.g. err.txt) for grep-after-run. Relative to repo root if not absolute."""
    raw = load_settings().get(KEY_DEBUG_LOG_PATH) or DEFAULT_DEBUG_LOG_PATH
    p = Path((raw or "").strip()).expanduser()
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


def get_ollama_host() -> str:
    """Return Ollama host URL, e.g. http://127.0.0.1:11434. Respects OLLAMA_HOST env."""
    return load_settings().get(KEY_OLLAMA_HOST) or _default_ollama_host()


def get_ollama_model() -> str:
    """Return Ollama model name to use for assistants chat. Respects OLLAMA_MODEL env."""
    return load_settings().get(KEY_OLLAMA_MODEL) or _default_ollama_model()


def list_llm_providers() -> list[str]:
    """List available provider module names under `LLM_integrations/`."""
    d = REPO_ROOT / "LLM_integrations"
    out: list[str] = []
    try:
        for p in d.glob("*.py"):
            name = p.stem
            if name in ("__init__", "client"):
                continue
            out.append(name)
    except OSError:
        pass
    # Ensure ollama is always shown (even if filesystem listing fails).
    if "ollama" not in out:
        out.append("ollama")
    return sorted(set(out))


def get_llm_provider(*, assistant: str) -> str:
    """
    Return selected LLM provider adapter name (e.g. 'ollama') for a given assistant profile.
    assistant: role id under ``assistants/roles/<id>/`` (e.g. workflow_designer, rl_coach, analyst).
    """
    a = (assistant or "").strip().lower() or "workflow_designer"
    return _role_llm_str(a, "provider", default=DEFAULT_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER


def get_llm_provider_config(*, assistant: str) -> dict:
    """
    Return provider config dict passed into `LLM_integrations.client.chat`.
    If config JSON is empty and provider=='ollama', derive from assistant-specific ollama_host/ollama_model.
    """
    data = load_settings()
    a = (assistant or "").strip().lower() or "workflow_designer"
    wd_host = _role_llm_str("workflow_designer", "ollama_host", default="")
    wd_model = _role_llm_str("workflow_designer", "ollama_model", default="")
    prov = _role_llm_str(a, "provider", default=DEFAULT_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER
    raw = _role_llm_str(a, "provider_config_json", default="")
    if a == "workflow_designer":
        legacy_h = data.get(KEY_OLLAMA_HOST)
        legacy_m = data.get(KEY_OLLAMA_MODEL)
        ollama_host = (
            wd_host
            or (str(legacy_h).strip() if legacy_h is not None else "")
            or _default_ollama_host()
        )
        ollama_model = (
            wd_model
            or (str(legacy_m).strip() if legacy_m is not None else "")
            or _default_ollama_model()
        )
    else:
        ollama_host = (
            _role_llm_str(a, "ollama_host", default="")
            or wd_host
            or _default_ollama_host()
        )
        ollama_model = (
            _role_llm_str(a, "ollama_model", default="")
            or wd_model
            or _default_ollama_model()
        )

    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                out = dict(parsed)
                # Merge api_key for Ollama Cloud: env > settings > JSON
                if prov == "ollama":
                    api_key = (
                        (os.environ.get("OLLAMA_API_KEY") or "").strip()
                        or (data.get(KEY_OLLAMA_API_KEY) or "").strip()
                        or (out.get("api_key") or "").strip()
                    )
                    if api_key:
                        out["api_key"] = api_key
                return out
        except json.JSONDecodeError:
            pass
    if prov == "ollama":
        out = {"host": ollama_host or _default_ollama_host(), "model": ollama_model or _default_ollama_model()}
        api_key = (os.environ.get("OLLAMA_API_KEY") or "").strip() or (data.get(KEY_OLLAMA_API_KEY) or "").strip()
        if api_key:
            out["api_key"] = api_key
        return out
    return {}


def get_chat_history_dir() -> Path:
    """Return resolved directory path where chat histories are stored."""
    raw = load_settings().get(KEY_CHAT_HISTORY_DIR) or _default_chat_history_dir()
    return _resolve_dir(str(raw))


def get_rag_index_dir() -> Path:
    """Return resolved directory for RAG index storage (chroma_db + .rag_index_state.json). Creates dir if needed."""
    from rag.ragconf_loader import rag_index_data_dir_raw

    raw = rag_index_data_dir_raw()
    path = _resolve_dir(str(raw))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_mydata_dir() -> Path:
    """Return resolved directory for mydata content (workflows, nodes, docs) to be indexed. No index files here."""
    raw = load_settings().get(KEY_MYDATA_DIR) or DEFAULT_MYDATA_DIR
    return _resolve_dir(str(raw))


def get_rag_embedding_model() -> str:
    """Return the embedding model name for RAG (sentence-transformers), from ``rag/ragconf.yaml``."""
    from rag.ragconf_loader import rag_embedding_model_raw

    return rag_embedding_model_raw()


def get_rag_offline() -> bool:
    """When True, RAG uses only cached embedding model (HF_HUB_OFFLINE=1). From ``rag/ragconf.yaml``."""
    from rag.ragconf_loader import rag_offline_raw

    return rag_offline_raw()


def get_rag_top_k() -> int:
    """RagSearch top_k for non–Workflow Designer chat RAG (``assistants/roles/rl_coach/role.yaml`` ``rag.top_k``)."""
    from units.canonical.app_settings_param import resolve_param_ref

    raw = resolve_param_ref("role.rl_coach.rag.top_k")
    if raw is None:
        return max(1, min(50, int(DEFAULT_RAG_TOP_K)))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_RAG_TOP_K
    return max(1, min(50, n))


def get_role_rag_top_k(role_id: str) -> int:
    """RagSearch top_k from ``assistants/roles/<role_id>/role.yaml`` ``rag.top_k`` (chat assistants)."""
    from units.canonical.app_settings_param import resolve_param_ref

    rid = (role_id or "").strip()
    if not rid:
        return max(1, min(50, int(DEFAULT_WORKFLOW_DESIGNER_RAG_TOP_K)))
    raw = resolve_param_ref(f"role.{rid}.rag.top_k")
    if raw is None:
        return max(1, min(50, int(DEFAULT_WORKFLOW_DESIGNER_RAG_TOP_K)))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_WORKFLOW_DESIGNER_RAG_TOP_K
    return max(1, min(50, n))


def get_workflow_designer_rag_top_k() -> int:
    """RagSearch top_k for Workflow Designer (``assistants/roles/workflow_designer/role.yaml`` ``rag.top_k``)."""
    return get_role_rag_top_k("workflow_designer")


def get_rag_min_score() -> float:
    """Minimum similarity score for RAG filter (``assistants/tools/rag_search/tool.yaml`` ``rag.min_score``)."""
    from units.canonical.app_settings_param import resolve_param_ref

    raw = resolve_param_ref("tool.rag_search.rag.min_score")
    if raw is None:
        return max(0.0, min(1.0, float(DEFAULT_RAG_MIN_SCORE)))
    try:
        x = float(raw)
    except (TypeError, ValueError):
        x = DEFAULT_RAG_MIN_SCORE
    return max(0.0, min(1.0, x))


def get_rag_format_max_chars() -> int:
    """FormatRagPrompt max total chars (``assistants/tools/rag_search/tool.yaml`` ``rag.format_max_chars``)."""
    from units.canonical.app_settings_param import resolve_param_ref

    raw = resolve_param_ref("tool.rag_search.rag.format_max_chars")
    if raw is None:
        return max(1, min(5000, int(DEFAULT_RAG_FORMAT_MAX_CHARS)))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_RAG_FORMAT_MAX_CHARS
    return max(1, min(5000, n))


def get_rag_format_snippet_max() -> int:
    """FormatRagPrompt per-snippet cap (``assistants/tools/rag_search/tool.yaml`` ``rag.format_snippet_max``)."""
    from units.canonical.app_settings_param import resolve_param_ref

    raw = resolve_param_ref("tool.rag_search.rag.format_snippet_max")
    if raw is None:
        return max(1, min(2000, int(DEFAULT_RAG_FORMAT_SNIPPET_MAX)))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_RAG_FORMAT_SNIPPET_MAX
    return max(1, min(2000, int(n)))


def get_read_file_rag_max_chars() -> int:
    """FormatRagPrompt max_chars for read_file path RAG (``assistants/tools/read_file/tool.yaml`` ``rag.max_chars``)."""
    from units.canonical.app_settings_param import resolve_param_ref

    raw = resolve_param_ref("tool.read_file.rag.max_chars")
    if raw is None:
        return max(1, min(5000, int(DEFAULT_READ_FILE_RAG_MAX_CHARS)))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_READ_FILE_RAG_MAX_CHARS
    return max(1, min(5000, n))


def get_read_file_rag_snippet_max() -> int:
    """FormatRagPrompt snippet_max for read_file (``assistants/tools/read_file/tool.yaml`` ``rag.snippet_max``)."""
    from units.canonical.app_settings_param import resolve_param_ref

    raw = resolve_param_ref("tool.read_file.rag.snippet_max")
    if raw is None:
        return max(1, min(5000, int(DEFAULT_READ_FILE_RAG_SNIPPET_MAX)))
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_READ_FILE_RAG_SNIPPET_MAX
    return max(1, min(5000, n))


def get_coding_is_allowed() -> bool:
    """When True, Workflow Designer shows add_code_block and allows custom code on function units."""
    return bool(load_settings().get(KEY_CODING_IS_ALLOWED, DEFAULT_CODING_IS_ALLOWED))


def get_contribution_is_allowed() -> bool:
    """When True (with native runtime and coding_is_allowed), WD system prompt includes list_unit / list_environment lines."""
    return bool(load_settings().get(KEY_CONTRIBUTION_IS_ALLOWED, DEFAULT_CONTRIBUTION_IS_ALLOWED))


def get_auto_delegation_is_allowed() -> bool:
    """When True, Analyst chat runs auto_delegate_workflow (RAG TeamMember pick) before the main workflow."""
    return bool(load_settings().get(KEY_AUTO_DELEGATION_IS_ALLOWED, DEFAULT_AUTO_DELEGATION_IS_ALLOWED))


def get_auto_delegate_workflow_path() -> Path:
    """Bundled graph: user message → RAG context workflow → delegate_request (see assistants/tools/delegate_request/)."""
    return (REPO_ROOT / "assistants/tools/delegate_request/auto_delegate_workflow.json").resolve()


def _coerce_llm_generation_options(
    temp_raw: Any,
    num_predict_raw: Any,
    *,
    default_temperature: float,
    default_num_predict: int,
) -> dict[str, Any]:
    """Build Ollama-compatible options dict for LLMAgent (temperature, num_predict)."""
    try:
        t = float(temp_raw)
    except (TypeError, ValueError):
        t = default_temperature
    t = max(0.0, min(2.0, t))
    try:
        n = int(num_predict_raw)
    except (TypeError, ValueError):
        n = default_num_predict
    n = max(1, min(131072, n))
    return {"temperature": t, "num_predict": n}


def get_workflow_designer_llm_generation_options() -> dict[str, Any]:
    """Ollama options for Workflow Designer assistant workflows (LLMAgent.params['options'])."""
    return get_role_llm_generation_options("workflow_designer")


def get_role_llm_generation_options(role_id: str) -> dict[str, Any]:
    """Ollama options from ``assistants/roles/<role_id>/role.yaml`` ``llm`` (temperature, num_predict)."""
    rid = (role_id or "").strip() or "workflow_designer"
    return _coerce_llm_generation_options(
        _role_llm_float(rid, "temperature", default=DEFAULT_WD_LLM_TEMPERATURE),
        _role_llm_int(rid, "num_predict", default=DEFAULT_WD_LLM_NUM_PREDICT),
        default_temperature=DEFAULT_WD_LLM_TEMPERATURE,
        default_num_predict=DEFAULT_WD_LLM_NUM_PREDICT,
    )


def get_rl_coach_llm_generation_options() -> dict[str, Any]:
    """Ollama options for RL Coach workflow LLMAgent."""
    return get_role_llm_generation_options("rl_coach")


def get_workflow_designer_max_follow_ups() -> int:
    """Max parser/tool follow-up iterations and post-apply review rounds (``role.yaml`` ``follow_up_max_rounds``)."""
    try:
        from assistants.roles import WORKFLOW_DESIGNER_ROLE_ID, get_role

        fur = get_role(WORKFLOW_DESIGNER_ROLE_ID).follow_up_max_rounds
        if fur is not None:
            return max(
                MIN_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
                min(MAX_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS, int(fur)),
            )
    except Exception:
        pass
    return max(
        MIN_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
        min(MAX_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS, int(DEFAULT_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS)),
    )


def get_workflow_undo_max_depth() -> int:
    raw = load_settings().get(KEY_WORKFLOW_UNDO_MAX_DEPTH, DEFAULT_WORKFLOW_UNDO_MAX_DEPTH)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_WORKFLOW_UNDO_MAX_DEPTH
    return max(MIN_WORKFLOW_UNDO_MAX_DEPTH, min(MAX_WORKFLOW_UNDO_MAX_DEPTH, n))


def get_chat_stream_ui_interval_ms() -> int:
    raw = load_settings().get(KEY_CHAT_STREAM_UI_INTERVAL_MS, DEFAULT_CHAT_STREAM_UI_INTERVAL_MS)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_CHAT_STREAM_UI_INTERVAL_MS
    return max(MIN_CHAT_STREAM_UI_INTERVAL_MS, min(MAX_CHAT_STREAM_UI_INTERVAL_MS, n))

