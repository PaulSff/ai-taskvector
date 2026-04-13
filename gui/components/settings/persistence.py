"""Load and save ``config/app_settings.json``."""
from __future__ import annotations

import json
from typing import Any

from .constants import (
    DEFAULT_BEST_MODEL_PATH,
    DEFAULT_CHAT_HISTORY_DIR,
    DEFAULT_CODING_IS_ALLOWED,
    DEFAULT_CONTRIBUTION_IS_ALLOWED,
    DEFAULT_CREATE_FILENAME_PROMPT_PATH,
    DEFAULT_CREATE_FILENAME_WORKFLOW_PATH,
    DEFAULT_DEBUG_LOG_PATH,
    DEFAULT_LLM_PROVIDER,
    DEFAULT_MYDATA_DIR,
    DEFAULT_PROJECT_NAME,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_RL_COACH_PROMPT_PATH,
    DEFAULT_TRAINING_CONFIG_PATH,
    DEFAULT_WINDOW_HEIGHT,
    DEFAULT_WINDOW_WIDTH,
    DEFAULT_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
    DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH,
    DEFAULT_WORKFLOW_SAVE_PATH_TEMPLATE,
    KEY_BEST_MODEL_PATH,
    KEY_CHAT_HISTORY_DIR,
    KEY_CHAT_STREAM_UI_INTERVAL_MS,
    KEY_CODING_IS_ALLOWED,
    KEY_CONTRIBUTION_IS_ALLOWED,
    KEY_CREATE_FILENAME_PROMPT_PATH,
    KEY_CREATE_FILENAME_WORKFLOW_PATH,
    KEY_DEBUG_LOG_PATH,
    KEY_MYDATA_DIR,
    KEY_OLLAMA_API_KEY,
    KEY_OLLAMA_EXECUTABLE_PATH,
    KEY_OLLAMA_HOST,
    KEY_OLLAMA_MODEL,
    KEY_RAG_EMBEDDING_MODEL,
    KEY_RAG_INDEX_DATA_DIR,
    KEY_RAG_OFFLINE,
    KEY_RAG_UPDATE_WORKFLOW_PATH,
    KEY_RL_COACH_PROMPT_PATH,
    KEY_START_OLLAMA_WITH_APP,
    KEY_TRAINING_CONFIG_PATH,
    KEY_WINDOW_HEIGHT,
    KEY_WINDOW_WIDTH,
    KEY_WORKFLOW_DESIGNER_PROMPT_PATH,
    KEY_WORKFLOW_PROJECT_NAME,
    KEY_WORKFLOW_SAVE_PATH_TEMPLATE,
    KEY_WORKFLOW_UNDO_MAX_DEPTH,
    MAX_CHAT_STREAM_UI_INTERVAL_MS,
    MAX_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
    MAX_WORKFLOW_UNDO_MAX_DEPTH,
    MIN_CHAT_STREAM_UI_INTERVAL_MS,
    MIN_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
    MIN_WORKFLOW_UNDO_MAX_DEPTH,
    DEFAULT_CHAT_STREAM_UI_INTERVAL_MS,
    DEFAULT_WORKFLOW_UNDO_MAX_DEPTH,
    DEFAULT_RAG_EMBEDDING_MODEL,
)
from .paths import CONFIG_DIR, REPO_ROOT, SETTINGS_PATH, _resolve_dir
from .role_yaml import _patch_role_document, _patch_role_llm


def _default_chat_history_dir() -> str:
    return DEFAULT_CHAT_HISTORY_DIR


def _default_project_name() -> str:
    return DEFAULT_PROJECT_NAME


def _default_workflow_save_path_template() -> str:
    return DEFAULT_WORKFLOW_SAVE_PATH_TEMPLATE


def load_settings() -> dict:
    """Load settings from config/app_settings.json. Creates config dir and default file if missing."""
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    (REPO_ROOT / "config" / "my_workflows").mkdir(parents=True, exist_ok=True)
    _resolve_dir(_default_chat_history_dir()).mkdir(parents=True, exist_ok=True)
    if not SETTINGS_PATH.exists():
        default = {
            KEY_WORKFLOW_PROJECT_NAME: _default_project_name(),
            KEY_WORKFLOW_SAVE_PATH_TEMPLATE: _default_workflow_save_path_template(),
            KEY_TRAINING_CONFIG_PATH: DEFAULT_TRAINING_CONFIG_PATH,
            KEY_BEST_MODEL_PATH: DEFAULT_BEST_MODEL_PATH,
            KEY_CHAT_HISTORY_DIR: _default_chat_history_dir(),
            KEY_MYDATA_DIR: DEFAULT_MYDATA_DIR,
            KEY_CODING_IS_ALLOWED: DEFAULT_CODING_IS_ALLOWED,
            KEY_CONTRIBUTION_IS_ALLOWED: DEFAULT_CONTRIBUTION_IS_ALLOWED,
            KEY_WORKFLOW_UNDO_MAX_DEPTH: DEFAULT_WORKFLOW_UNDO_MAX_DEPTH,
            KEY_CHAT_STREAM_UI_INTERVAL_MS: DEFAULT_CHAT_STREAM_UI_INTERVAL_MS,
            KEY_WORKFLOW_DESIGNER_PROMPT_PATH: DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH,
            KEY_RL_COACH_PROMPT_PATH: DEFAULT_RL_COACH_PROMPT_PATH,
            KEY_CREATE_FILENAME_PROMPT_PATH: DEFAULT_CREATE_FILENAME_PROMPT_PATH,
            KEY_DEBUG_LOG_PATH: DEFAULT_DEBUG_LOG_PATH,
            KEY_WINDOW_WIDTH: DEFAULT_WINDOW_WIDTH,
            KEY_WINDOW_HEIGHT: DEFAULT_WINDOW_HEIGHT,
        }
        try:
            SETTINGS_PATH.write_text(json.dumps(default, indent=2), encoding="utf-8")
        except OSError:
            pass
        return default
    try:
        data = json.loads(SETTINGS_PATH.read_text(encoding="utf-8"))
        if not isinstance(data, dict):
            return {
                KEY_WORKFLOW_PROJECT_NAME: _default_project_name(),
                KEY_WORKFLOW_SAVE_PATH_TEMPLATE: _default_workflow_save_path_template(),
            }

        # Back-compat: older setting used a single workflow_save_path; keep it but prefer template+project.
        added_coding_is_allowed = False
        if KEY_WORKFLOW_PROJECT_NAME not in data:
            data[KEY_WORKFLOW_PROJECT_NAME] = _default_project_name()
        if KEY_WORKFLOW_SAVE_PATH_TEMPLATE not in data:
            data[KEY_WORKFLOW_SAVE_PATH_TEMPLATE] = _default_workflow_save_path_template()
        if KEY_TRAINING_CONFIG_PATH not in data:
            data[KEY_TRAINING_CONFIG_PATH] = DEFAULT_TRAINING_CONFIG_PATH
        if KEY_BEST_MODEL_PATH not in data:
            data[KEY_BEST_MODEL_PATH] = DEFAULT_BEST_MODEL_PATH

        if KEY_CHAT_HISTORY_DIR not in data:
            data[KEY_CHAT_HISTORY_DIR] = _default_chat_history_dir()
        if KEY_MYDATA_DIR not in data:
            data[KEY_MYDATA_DIR] = DEFAULT_MYDATA_DIR
        if KEY_CODING_IS_ALLOWED not in data:
            data[KEY_CODING_IS_ALLOWED] = DEFAULT_CODING_IS_ALLOWED
            added_coding_is_allowed = True
        if KEY_CONTRIBUTION_IS_ALLOWED not in data:
            data[KEY_CONTRIBUTION_IS_ALLOWED] = DEFAULT_CONTRIBUTION_IS_ALLOWED
        if KEY_WORKFLOW_UNDO_MAX_DEPTH not in data:
            data[KEY_WORKFLOW_UNDO_MAX_DEPTH] = DEFAULT_WORKFLOW_UNDO_MAX_DEPTH
        if KEY_CHAT_STREAM_UI_INTERVAL_MS not in data:
            data[KEY_CHAT_STREAM_UI_INTERVAL_MS] = DEFAULT_CHAT_STREAM_UI_INTERVAL_MS
        migrated_rag_workflows = False
        if "rag_context_workflow_path" in data:
            data.pop("rag_context_workflow_path", None)
            migrated_rag_workflows = True
        _rag_workflow_path_patch: dict[str, Any] = {}
        if KEY_RAG_UPDATE_WORKFLOW_PATH in data:
            v = data.pop(KEY_RAG_UPDATE_WORKFLOW_PATH)
            migrated_rag_workflows = True
            if isinstance(v, str) and v.strip():
                _rag_workflow_path_patch["rag_update_workflow_path"] = v.strip()
        if "doc_to_text_workflow_path" in data:
            v = data.pop("doc_to_text_workflow_path")
            migrated_rag_workflows = True
            if isinstance(v, str) and v.strip():
                _rag_workflow_path_patch["doc_to_text_workflow_path"] = v.strip()
        if _rag_workflow_path_patch:
            try:
                from rag.ragconf_loader import update_ragconf

                update_ragconf(_rag_workflow_path_patch)
            except Exception:
                pass
        migrated_create_filename_wp = False
        if KEY_CREATE_FILENAME_WORKFLOW_PATH in data:
            cfn = data.get(KEY_CREATE_FILENAME_WORKFLOW_PATH)
            cfn_s = (cfn if isinstance(cfn, str) else "").strip().replace("\\", "/")
            if not cfn_s or cfn_s == "assistants/create_filename.json":
                data.pop(KEY_CREATE_FILENAME_WORKFLOW_PATH, None)
                migrated_create_filename_wp = True
            elif cfn_s == str(DEFAULT_CREATE_FILENAME_WORKFLOW_PATH).replace("\\", "/"):
                # Shipped default path: use ``chat_name_creator`` role.yaml ``chat.workflow`` instead.
                data.pop(KEY_CREATE_FILENAME_WORKFLOW_PATH, None)
                migrated_create_filename_wp = True
        if KEY_CREATE_FILENAME_PROMPT_PATH not in data:
            data[KEY_CREATE_FILENAME_PROMPT_PATH] = DEFAULT_CREATE_FILENAME_PROMPT_PATH
        if migrated_rag_workflows or migrated_create_filename_wp:
            try:
                SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except OSError:
                pass
        if KEY_WORKFLOW_DESIGNER_PROMPT_PATH not in data:
            data[KEY_WORKFLOW_DESIGNER_PROMPT_PATH] = DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH
        if KEY_RL_COACH_PROMPT_PATH not in data:
            data[KEY_RL_COACH_PROMPT_PATH] = DEFAULT_RL_COACH_PROMPT_PATH
        if KEY_DEBUG_LOG_PATH not in data:
            data[KEY_DEBUG_LOG_PATH] = DEFAULT_DEBUG_LOG_PATH
        if KEY_WINDOW_WIDTH not in data:
            data[KEY_WINDOW_WIDTH] = DEFAULT_WINDOW_WIDTH
        if KEY_WINDOW_HEIGHT not in data:
            data[KEY_WINDOW_HEIGHT] = DEFAULT_WINDOW_HEIGHT
        if KEY_START_OLLAMA_WITH_APP not in data:
            data[KEY_START_OLLAMA_WITH_APP] = False
        if KEY_OLLAMA_EXECUTABLE_PATH not in data:
            data[KEY_OLLAMA_EXECUTABLE_PATH] = ""
        if added_coding_is_allowed:
            try:
                SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except OSError:
                pass
        # Main WD/RL chat workflows now come from assistants/roles/<id>/role.yaml (chat.workflow).
        _legacy_chat_workflow_keys = ("assistant_workflow_path", "rl_coach_workflow_path")
        if any(k in data for k in _legacy_chat_workflow_keys):
            for k in _legacy_chat_workflow_keys:
                data.pop(k, None)
            try:
                SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except OSError:
                pass
        # WD follow-up tool graphs now live under assistants/tools/<id>/tool.yaml (no app_settings paths).
        _legacy_tool_workflow_path_keys = (
            "web_search_workflow_path",
            "browser_workflow_path",
            "github_get_workflow_path",
        )
        if any(k in data for k in _legacy_tool_workflow_path_keys):
            for k in _legacy_tool_workflow_path_keys:
                data.pop(k, None)
            try:
                SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except OSError:
                pass
        _legacy_rag_keys = (KEY_RAG_INDEX_DATA_DIR, KEY_RAG_EMBEDDING_MODEL, KEY_RAG_OFFLINE)
        if any(k in data for k in _legacy_rag_keys):
            from rag.ragconf_loader import update_ragconf

            patch: dict[str, Any] = {}
            if KEY_RAG_INDEX_DATA_DIR in data:
                v = data.pop(KEY_RAG_INDEX_DATA_DIR)
                s = (str(v).strip() if v is not None else "")
                if s:
                    patch["rag_index_data_dir"] = s
            if KEY_RAG_EMBEDDING_MODEL in data:
                v = data.pop(KEY_RAG_EMBEDDING_MODEL)
                s = (str(v).strip() if v is not None else "")
                if s:
                    patch["rag_embedding_model"] = s
            if KEY_RAG_OFFLINE in data:
                patch["rag_offline"] = bool(data.pop(KEY_RAG_OFFLINE))
            if patch:
                update_ragconf(patch)
            try:
                SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")
            except OSError:
                pass
        return data
    except (json.JSONDecodeError, OSError):
        return {
            KEY_WORKFLOW_PROJECT_NAME: _default_project_name(),
            KEY_WORKFLOW_SAVE_PATH_TEMPLATE: _default_workflow_save_path_template(),
        }


def save_settings(
    *,
    workflow_project_name: str | None = None,
    workflow_save_path_template: str | None = None,
    workflow_designer_llm_provider: str | None = None,
    workflow_designer_llm_provider_config_json: str | None = None,
    workflow_designer_ollama_host: str | None = None,
    workflow_designer_ollama_model: str | None = None,
    rl_coach_llm_provider: str | None = None,
    rl_coach_llm_provider_config_json: str | None = None,
    rl_coach_ollama_host: str | None = None,
    rl_coach_ollama_model: str | None = None,
    role_llm_updates: dict[str, dict[str, Any]] | None = None,
    ollama_api_key: str | None = None,
    start_ollama_with_app: bool | None = None,
    ollama_executable_path: str | None = None,
    ollama_host: str | None = None,
    ollama_model: str | None = None,
    chat_history_dir: str | None = None,
    mydata_dir: str | None = None,
    rag_embedding_model: str | None = None,
    rag_offline: bool | None = None,
    coding_is_allowed: bool | None = None,
    contribution_is_allowed: bool | None = None,
    workflow_designer_max_follow_ups: int | None = None,
    workflow_undo_max_depth: int | None = None,
    chat_stream_ui_interval_ms: int | None = None,
    debug_log_path: str | None = None,
    create_filename_workflow_path: str | None = None,
    workflow_designer_prompt_path: str | None = None,
    rl_coach_prompt_path: str | None = None,
    create_filename_prompt_path: str | None = None,
    training_config_path: str | None = None,
    best_model_path: str | None = None,
    window_width: int | None = None,
    window_height: int | None = None,
) -> None:
    """Write settings to config/app_settings.json (only provided fields are updated).

    When ``role_llm_updates`` is not None, each role's ``llm`` block in ``role.yaml`` is patched from that
    dict (Settings tab). Otherwise legacy ``workflow_designer_*`` / ``rl_coach_*`` LLM keyword arguments apply.
    """
    CONFIG_DIR.mkdir(parents=True, exist_ok=True)
    data = load_settings()
    if workflow_project_name is not None:
        data[KEY_WORKFLOW_PROJECT_NAME] = (workflow_project_name or "").strip() or _default_project_name()
    if workflow_save_path_template is not None:
        data[KEY_WORKFLOW_SAVE_PATH_TEMPLATE] = (
            (workflow_save_path_template or "").strip() or _default_workflow_save_path_template()
        )
    if training_config_path is not None:
        data[KEY_TRAINING_CONFIG_PATH] = (
            (training_config_path or "").strip() or DEFAULT_TRAINING_CONFIG_PATH
        )
    if best_model_path is not None:
        data[KEY_BEST_MODEL_PATH] = (best_model_path or "").strip()
    # Per-assistant LLM updates (role.yaml ``llm:``)
    if role_llm_updates is not None:
        for rid, patch in role_llm_updates.items():
            role_key = (rid or "").strip()
            if not role_key or not isinstance(patch, dict):
                continue
            merged = {k: v for k, v in patch.items() if v is not None}
            if merged:
                _patch_role_llm(role_key, merged)
    else:
        wd_llm_patch: dict[str, Any] = {}
        if workflow_designer_llm_provider is not None:
            wd_llm_patch["provider"] = (workflow_designer_llm_provider or "").strip() or DEFAULT_LLM_PROVIDER
        if workflow_designer_llm_provider_config_json is not None:
            wd_llm_patch["provider_config_json"] = (workflow_designer_llm_provider_config_json or "").strip()
        if workflow_designer_ollama_host is not None:
            wd_llm_patch["ollama_host"] = (workflow_designer_ollama_host or "").strip() or DEFAULT_OLLAMA_HOST
        if workflow_designer_ollama_model is not None:
            wd_llm_patch["ollama_model"] = (workflow_designer_ollama_model or "").strip() or DEFAULT_OLLAMA_MODEL
        if wd_llm_patch:
            _patch_role_llm("workflow_designer", wd_llm_patch)

        rl_llm_patch: dict[str, Any] = {}
        if rl_coach_llm_provider is not None:
            rl_llm_patch["provider"] = (rl_coach_llm_provider or "").strip() or DEFAULT_LLM_PROVIDER
        if rl_coach_llm_provider_config_json is not None:
            rl_llm_patch["provider_config_json"] = (rl_coach_llm_provider_config_json or "").strip()
        if rl_coach_ollama_host is not None:
            rl_llm_patch["ollama_host"] = (rl_coach_ollama_host or "").strip() or DEFAULT_OLLAMA_HOST
        if rl_coach_ollama_model is not None:
            rl_llm_patch["ollama_model"] = (rl_coach_ollama_model or "").strip() or DEFAULT_OLLAMA_MODEL
        if rl_llm_patch:
            _patch_role_llm("rl_coach", rl_llm_patch)

    if ollama_api_key is not None:
        data[KEY_OLLAMA_API_KEY] = (ollama_api_key or "").strip()

    if start_ollama_with_app is not None:
        data[KEY_START_OLLAMA_WITH_APP] = bool(start_ollama_with_app)
    if ollama_executable_path is not None:
        data[KEY_OLLAMA_EXECUTABLE_PATH] = (ollama_executable_path or "").strip()

    # Legacy/global updates (deprecated). Kept only for back-compat; avoid using in new code.
    if ollama_host is not None:
        data[KEY_OLLAMA_HOST] = (ollama_host or "").strip() or DEFAULT_OLLAMA_HOST
    if ollama_model is not None:
        data[KEY_OLLAMA_MODEL] = (ollama_model or "").strip() or DEFAULT_OLLAMA_MODEL
    if chat_history_dir is not None:
        data[KEY_CHAT_HISTORY_DIR] = (chat_history_dir or "").strip() or _default_chat_history_dir()
    if mydata_dir is not None:
        data[KEY_MYDATA_DIR] = (mydata_dir or "").strip() or DEFAULT_MYDATA_DIR
    ragconf_patch: dict[str, Any] = {}
    if rag_embedding_model is not None:
        ragconf_patch["rag_embedding_model"] = (rag_embedding_model or "").strip() or DEFAULT_RAG_EMBEDDING_MODEL
    if rag_offline is not None:
        ragconf_patch["rag_offline"] = bool(rag_offline)
    if ragconf_patch:
        from rag.ragconf_loader import update_ragconf

        update_ragconf(ragconf_patch)
    if coding_is_allowed is not None:
        data[KEY_CODING_IS_ALLOWED] = bool(coding_is_allowed)
    if contribution_is_allowed is not None:
        data[KEY_CONTRIBUTION_IS_ALLOWED] = bool(contribution_is_allowed)
    if workflow_designer_max_follow_ups is not None:
        try:
            n = int(workflow_designer_max_follow_ups)
        except (TypeError, ValueError):
            n = DEFAULT_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS
        n = max(
            MIN_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
            min(MAX_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS, n),
        )
        _patch_role_document("workflow_designer", {"follow_up_max_rounds": n})
    if workflow_undo_max_depth is not None:
        try:
            n = int(workflow_undo_max_depth)
        except (TypeError, ValueError):
            n = DEFAULT_WORKFLOW_UNDO_MAX_DEPTH
        data[KEY_WORKFLOW_UNDO_MAX_DEPTH] = max(
            MIN_WORKFLOW_UNDO_MAX_DEPTH,
            min(MAX_WORKFLOW_UNDO_MAX_DEPTH, n),
        )
    if chat_stream_ui_interval_ms is not None:
        try:
            n = int(chat_stream_ui_interval_ms)
        except (TypeError, ValueError):
            n = DEFAULT_CHAT_STREAM_UI_INTERVAL_MS
        data[KEY_CHAT_STREAM_UI_INTERVAL_MS] = max(
            MIN_CHAT_STREAM_UI_INTERVAL_MS,
            min(MAX_CHAT_STREAM_UI_INTERVAL_MS, n),
        )
    if debug_log_path is not None:
        data[KEY_DEBUG_LOG_PATH] = (debug_log_path or "").strip() or DEFAULT_DEBUG_LOG_PATH
    if create_filename_workflow_path is not None:
        v = (create_filename_workflow_path or "").strip()
        if not v:
            data.pop(KEY_CREATE_FILENAME_WORKFLOW_PATH, None)
        else:
            data[KEY_CREATE_FILENAME_WORKFLOW_PATH] = v
    if workflow_designer_prompt_path is not None:
        data[KEY_WORKFLOW_DESIGNER_PROMPT_PATH] = (workflow_designer_prompt_path or "").strip() or DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH
    if rl_coach_prompt_path is not None:
        data[KEY_RL_COACH_PROMPT_PATH] = (rl_coach_prompt_path or "").strip() or DEFAULT_RL_COACH_PROMPT_PATH
    if create_filename_prompt_path is not None:
        data[KEY_CREATE_FILENAME_PROMPT_PATH] = (create_filename_prompt_path or "").strip() or DEFAULT_CREATE_FILENAME_PROMPT_PATH
    if window_width is not None and window_width > 0:
        data[KEY_WINDOW_WIDTH] = int(window_width)
    if window_height is not None and window_height > 0:
        data[KEY_WINDOW_HEIGHT] = int(window_height)
    for _rk in (
        KEY_RAG_INDEX_DATA_DIR,
        KEY_RAG_EMBEDDING_MODEL,
        KEY_RAG_OFFLINE,
        "rag_context_workflow_path",
        KEY_RAG_UPDATE_WORKFLOW_PATH,
        "doc_to_text_workflow_path",
    ):
        data.pop(_rk, None)
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Ensure dirs exist (best effort)
    try:
        _resolve_dir(str(data.get(KEY_CHAT_HISTORY_DIR) or _default_chat_history_dir())).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass
