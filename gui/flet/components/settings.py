"""
Settings tab: store app preferences (e.g. workflow save path) in config JSON.
Default workflow path template:
  config/my_workflows/$PROJECT_NAME$/$PROJECT_NAME$_workflow_$YY-MM-DD-HHMMSS$.json
"""
from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any, Callable

import flet as ft

from gui.flet.tools.notifications import show_toast

# Repo root: gui/flet/components/settings.py -> ... -> repo
_COMPONENTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = _COMPONENTS_DIR.parent.parent.parent

SETTINGS_FILENAME = "app_settings.json"
CONFIG_DIR = REPO_ROOT / "config"
SETTINGS_PATH = CONFIG_DIR / SETTINGS_FILENAME

# Workflow save settings (versioned saves)
DEFAULT_WORKFLOWS_DIR = "config/my_workflows"
DEFAULT_PROJECT_NAME = "my_project"
DEFAULT_WORKFLOW_SAVE_PATH_TEMPLATE = (
    "config/my_workflows/$PROJECT_NAME$/$PROJECT_NAME$_workflow_$YY-MM-DD-HHMMSS$.json"
)

KEY_WORKFLOW_PROJECT_NAME = "workflow_project_name"
KEY_WORKFLOW_SAVE_PATH_TEMPLATE = "workflow_save_path_template"
KEY_TRAINING_CONFIG_PATH = "training_config_path"
DEFAULT_TRAINING_CONFIG_PATH = "config/examples/training_config.yaml"
KEY_BEST_MODEL_PATH = "best_model_path"
DEFAULT_BEST_MODEL_PATH = ""

# LLM settings (per-assistant profiles)
#
# Back-compat note:
# - `ollama_host`, `ollama_model`, `llm_provider`, `llm_provider_config_json` were previously global.
# - We now store separate settings for Workflow Designer and RL Coach, but we still read the old keys
#   as defaults for Workflow Designer and for migration.
KEY_OLLAMA_HOST = "ollama_host"  # legacy/global
KEY_OLLAMA_MODEL = "ollama_model"  # legacy/global
DEFAULT_OLLAMA_HOST = "http://127.0.0.1:11434"
DEFAULT_OLLAMA_MODEL = "llama3.2"


def _default_ollama_host() -> str:
    """Default Ollama host; use OLLAMA_HOST env in Docker (e.g. http://ollama:11434)."""
    return (os.environ.get("OLLAMA_HOST") or "").strip() or DEFAULT_OLLAMA_HOST


def _default_ollama_model() -> str:
    """Default Ollama model; use OLLAMA_MODEL env to override."""
    return (os.environ.get("OLLAMA_MODEL") or "").strip() or DEFAULT_OLLAMA_MODEL

KEY_LLM_PROVIDER = "llm_provider"  # legacy/global
DEFAULT_LLM_PROVIDER = "ollama"
KEY_LLM_PROVIDER_CONFIG_JSON = "llm_provider_config_json"  # legacy/global
DEFAULT_LLM_PROVIDER_CONFIG_JSON = ""
# Optional: for Ollama Cloud (https://ollama.com); also use env OLLAMA_API_KEY
KEY_OLLAMA_API_KEY = "ollama_api_key"
# Start Ollama server with app (so you don't run "ollama serve" separately)
KEY_START_OLLAMA_WITH_APP = "start_ollama_with_app"
KEY_OLLAMA_EXECUTABLE_PATH = "ollama_executable_path"

# Workflow Designer profile
KEY_WD_LLM_PROVIDER = "workflow_designer_llm_provider"
KEY_WD_LLM_PROVIDER_CONFIG_JSON = "workflow_designer_llm_provider_config_json"
KEY_WD_OLLAMA_HOST = "workflow_designer_ollama_host"
KEY_WD_OLLAMA_MODEL = "workflow_designer_ollama_model"
# Ollama generation options for assistant workflows (passed to LLMAgent.params["options"])
KEY_WD_LLM_TEMPERATURE = "workflow_designer_llm_temperature"
KEY_WD_LLM_NUM_PREDICT = "workflow_designer_llm_num_predict"
DEFAULT_WD_LLM_TEMPERATURE = 0.3
DEFAULT_WD_LLM_NUM_PREDICT = 1024

# RL Coach profile
KEY_RL_LLM_PROVIDER = "rl_coach_llm_provider"
KEY_RL_LLM_PROVIDER_CONFIG_JSON = "rl_coach_llm_provider_config_json"
KEY_RL_OLLAMA_HOST = "rl_coach_ollama_host"
KEY_RL_OLLAMA_MODEL = "rl_coach_ollama_model"
KEY_RL_LLM_TEMPERATURE = "rl_coach_llm_temperature"
KEY_RL_LLM_NUM_PREDICT = "rl_coach_llm_num_predict"
DEFAULT_RL_LLM_TEMPERATURE = 0.3
DEFAULT_RL_LLM_NUM_PREDICT = 1024

# Chat history persistence (assistants chat)
KEY_CHAT_HISTORY_DIR = "chat_history_dir"
# Under mydata so RAG startup/update indexes saved chats with the rest of mydata.
DEFAULT_CHAT_HISTORY_DIR = "mydata/chat_history"

# RAG: index storage (chroma_db + state) vs mydata content
KEY_RAG_INDEX_DATA_DIR = "rag_index_data_dir"  # where chroma_db/ and .rag_index_state.json live
KEY_MYDATA_DIR = "mydata_dir"  # where user content to index lives (workflows, nodes, docs)
DEFAULT_RAG_INDEX_DATA_DIR = "rag/.rag_index_data"
DEFAULT_MYDATA_DIR = "mydata"

# RAG embedding model (sentence-transformers)
KEY_RAG_EMBEDDING_MODEL = "rag_embedding_model"
DEFAULT_RAG_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
# RAG offline: when True, set HF_HUB_OFFLINE=1 so only cached model is used (no network).
KEY_RAG_OFFLINE = "rag_offline"
DEFAULT_RAG_OFFLINE = False
# RAG context workflow (chat): RagSearch top_k, Filter score threshold, FormatRagPrompt caps; read_file path retrieval
KEY_RAG_TOP_K = "rag_top_k"
DEFAULT_RAG_TOP_K = 8
KEY_WORKFLOW_DESIGNER_RAG_TOP_K = "workflow_designer_rag_top_k"
DEFAULT_WORKFLOW_DESIGNER_RAG_TOP_K = 5
KEY_RAG_MIN_SCORE = "rag_min_score"
DEFAULT_RAG_MIN_SCORE = 0.48
KEY_RAG_FORMAT_MAX_CHARS = "rag_format_max_chars"
DEFAULT_RAG_FORMAT_MAX_CHARS = 1200
KEY_RAG_FORMAT_SNIPPET_MAX = "rag_format_snippet_max"
DEFAULT_RAG_FORMAT_SNIPPET_MAX = 400
KEY_READ_FILE_RAG_MAX_CHARS = "read_file_rag_max_chars"
DEFAULT_READ_FILE_RAG_MAX_CHARS = 8000
KEY_READ_FILE_RAG_SNIPPET_MAX = "read_file_rag_snippet_max"
DEFAULT_READ_FILE_RAG_SNIPPET_MAX = 4000

# Workflow Designer: allow add_code_block (custom code on function units). When False, only units from Units Library.
KEY_CODING_IS_ALLOWED = "coding_is_allowed"
DEFAULT_CODING_IS_ALLOWED = False
# Cap for parser/tool follow-up chain and post-apply review rounds (Workflow Designer chat).
KEY_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS = "workflow_designer_max_follow_ups"
DEFAULT_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS = 6
MIN_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS = 1
MAX_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS = 20
KEY_WORKFLOW_UNDO_MAX_DEPTH = "workflow_undo_max_depth"
DEFAULT_WORKFLOW_UNDO_MAX_DEPTH = 50
MIN_WORKFLOW_UNDO_MAX_DEPTH = 3
MAX_WORKFLOW_UNDO_MAX_DEPTH = 100
KEY_CHAT_STREAM_UI_INTERVAL_MS = "chat_stream_ui_interval_ms"
DEFAULT_CHAT_STREAM_UI_INTERVAL_MS = 60
MIN_CHAT_STREAM_UI_INTERVAL_MS = 16
MAX_CHAT_STREAM_UI_INTERVAL_MS = 300

# Assistant / chat workflow and prompt paths (relative to repo root; from app_settings.json where persisted)
KEY_WEB_SEARCH_WORKFLOW_PATH = "web_search_workflow_path"
KEY_BROWSER_WORKFLOW_PATH = "browser_workflow_path"
KEY_GITHUB_GET_WORKFLOW_PATH = "github_get_workflow_path"
KEY_RAG_CONTEXT_WORKFLOW_PATH = "rag_context_workflow_path"
KEY_RAG_UPDATE_WORKFLOW_PATH = "rag_update_workflow_path"
KEY_CREATE_FILENAME_WORKFLOW_PATH = "create_filename_workflow_path"
DEFAULT_WEB_SEARCH_WORKFLOW_PATH = "gui/flet/components/workflow/tools/web_search.json"
DEFAULT_BROWSER_WORKFLOW_PATH = "gui/flet/components/workflow/tools/browser.json"
DEFAULT_GITHUB_GET_WORKFLOW_PATH = "gui/flet/components/workflow/tools/github_get.json"
DEFAULT_RAG_CONTEXT_WORKFLOW_PATH = "gui/flet/components/workflow/assistants/rag_context_workflow.json"
DEFAULT_RAG_UPDATE_WORKFLOW_PATH = "gui/flet/components/workflow/assistants/rag_update.json"
DEFAULT_DOC_TO_TEXT_WORKFLOW_PATH = "gui/flet/components/workflow/assistants/doc_to_text.json"
DEFAULT_CREATE_FILENAME_WORKFLOW_PATH = "assistants/roles/chat_name_creator/create_filename.json"

# Prompt template paths for assistant workflows (relative to repo root)
KEY_WORKFLOW_DESIGNER_PROMPT_PATH = "workflow_designer_prompt_path"
KEY_RL_COACH_PROMPT_PATH = "rl_coach_prompt_path"
KEY_CREATE_FILENAME_PROMPT_PATH = "create_filename_prompt_path"
DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH = "config/prompts/workflow_designer.json"
DEFAULT_RL_COACH_PROMPT_PATH = "config/prompts/rl_coach.json"
DEFAULT_CREATE_FILENAME_PROMPT_PATH = "config/prompts/create_filename.json"

# Run console: path to log file (e.g. from Debug units) for grep workflow run after main run
KEY_DEBUG_LOG_PATH = "debug_log_path"
DEFAULT_DEBUG_LOG_PATH = "err.txt"

# Flet window size (persisted so last size is restored on startup; default ~30% larger than 1200x800)
KEY_WINDOW_WIDTH = "window_width"
KEY_WINDOW_HEIGHT = "window_height"
DEFAULT_WINDOW_WIDTH = 1560  # 1200 * 1.3
DEFAULT_WINDOW_HEIGHT = 1040  # 800 * 1.3


def _resolve_dir(value: str) -> Path:
    """
    Resolve a directory path from settings.
    - If absolute: use as-is
    - If relative: interpret relative to repo root
    """
    p = Path((value or "").strip()).expanduser()
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


def _resolve_workflow_path(value: str, default: str) -> Path:
    """Resolve a workflow or prompt file path from settings (relative to repo root if not absolute)."""
    raw = (value or "").strip() or default
    p = Path(raw).expanduser()
    if not p.is_absolute():
        p = REPO_ROOT / p
    return p


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
            # Per-assistant defaults
            KEY_WD_LLM_PROVIDER: DEFAULT_LLM_PROVIDER,
            KEY_WD_LLM_PROVIDER_CONFIG_JSON: DEFAULT_LLM_PROVIDER_CONFIG_JSON,
            KEY_WD_OLLAMA_HOST: DEFAULT_OLLAMA_HOST,
            KEY_WD_OLLAMA_MODEL: DEFAULT_OLLAMA_MODEL,
            KEY_WD_LLM_TEMPERATURE: DEFAULT_WD_LLM_TEMPERATURE,
            KEY_WD_LLM_NUM_PREDICT: DEFAULT_WD_LLM_NUM_PREDICT,
            KEY_RL_LLM_PROVIDER: DEFAULT_LLM_PROVIDER,
            KEY_RL_LLM_PROVIDER_CONFIG_JSON: DEFAULT_LLM_PROVIDER_CONFIG_JSON,
            KEY_RL_OLLAMA_HOST: DEFAULT_OLLAMA_HOST,
            KEY_RL_OLLAMA_MODEL: DEFAULT_OLLAMA_MODEL,
            KEY_RL_LLM_TEMPERATURE: DEFAULT_RL_LLM_TEMPERATURE,
            KEY_RL_LLM_NUM_PREDICT: DEFAULT_RL_LLM_NUM_PREDICT,
            KEY_CHAT_HISTORY_DIR: _default_chat_history_dir(),
            KEY_RAG_INDEX_DATA_DIR: DEFAULT_RAG_INDEX_DATA_DIR,
            KEY_MYDATA_DIR: DEFAULT_MYDATA_DIR,
            KEY_RAG_EMBEDDING_MODEL: DEFAULT_RAG_EMBEDDING_MODEL,
            KEY_RAG_OFFLINE: DEFAULT_RAG_OFFLINE,
            KEY_RAG_TOP_K: DEFAULT_RAG_TOP_K,
            KEY_WORKFLOW_DESIGNER_RAG_TOP_K: DEFAULT_WORKFLOW_DESIGNER_RAG_TOP_K,
            KEY_RAG_MIN_SCORE: DEFAULT_RAG_MIN_SCORE,
            KEY_RAG_FORMAT_MAX_CHARS: DEFAULT_RAG_FORMAT_MAX_CHARS,
            KEY_RAG_FORMAT_SNIPPET_MAX: DEFAULT_RAG_FORMAT_SNIPPET_MAX,
            KEY_READ_FILE_RAG_MAX_CHARS: DEFAULT_READ_FILE_RAG_MAX_CHARS,
            KEY_READ_FILE_RAG_SNIPPET_MAX: DEFAULT_READ_FILE_RAG_SNIPPET_MAX,
            KEY_CODING_IS_ALLOWED: DEFAULT_CODING_IS_ALLOWED,
            KEY_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS: DEFAULT_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
            KEY_WORKFLOW_UNDO_MAX_DEPTH: DEFAULT_WORKFLOW_UNDO_MAX_DEPTH,
            KEY_CHAT_STREAM_UI_INTERVAL_MS: DEFAULT_CHAT_STREAM_UI_INTERVAL_MS,
            KEY_WEB_SEARCH_WORKFLOW_PATH: DEFAULT_WEB_SEARCH_WORKFLOW_PATH,
            KEY_BROWSER_WORKFLOW_PATH: DEFAULT_BROWSER_WORKFLOW_PATH,
            KEY_GITHUB_GET_WORKFLOW_PATH: DEFAULT_GITHUB_GET_WORKFLOW_PATH,
            KEY_RAG_CONTEXT_WORKFLOW_PATH: DEFAULT_RAG_CONTEXT_WORKFLOW_PATH,
            KEY_RAG_UPDATE_WORKFLOW_PATH: DEFAULT_RAG_UPDATE_WORKFLOW_PATH,
            KEY_CREATE_FILENAME_WORKFLOW_PATH: DEFAULT_CREATE_FILENAME_WORKFLOW_PATH,
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

        # Per-assistant keys (migrate from legacy/global if missing)
        if KEY_WD_LLM_PROVIDER not in data:
            data[KEY_WD_LLM_PROVIDER] = data.get(KEY_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER
        if KEY_WD_LLM_PROVIDER_CONFIG_JSON not in data:
            data[KEY_WD_LLM_PROVIDER_CONFIG_JSON] = data.get(KEY_LLM_PROVIDER_CONFIG_JSON) or DEFAULT_LLM_PROVIDER_CONFIG_JSON
        if KEY_WD_OLLAMA_HOST not in data:
            data[KEY_WD_OLLAMA_HOST] = data.get(KEY_OLLAMA_HOST) or DEFAULT_OLLAMA_HOST
        if KEY_WD_OLLAMA_MODEL not in data:
            data[KEY_WD_OLLAMA_MODEL] = data.get(KEY_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL

        if KEY_RL_LLM_PROVIDER not in data:
            data[KEY_RL_LLM_PROVIDER] = data.get(KEY_WD_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER
        if KEY_RL_LLM_PROVIDER_CONFIG_JSON not in data:
            data[KEY_RL_LLM_PROVIDER_CONFIG_JSON] = data.get(KEY_WD_LLM_PROVIDER_CONFIG_JSON) or DEFAULT_LLM_PROVIDER_CONFIG_JSON
        if KEY_RL_OLLAMA_HOST not in data:
            data[KEY_RL_OLLAMA_HOST] = data.get(KEY_WD_OLLAMA_HOST) or DEFAULT_OLLAMA_HOST
        if KEY_RL_OLLAMA_MODEL not in data:
            data[KEY_RL_OLLAMA_MODEL] = data.get(KEY_WD_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL

        if KEY_WD_LLM_TEMPERATURE not in data:
            data[KEY_WD_LLM_TEMPERATURE] = DEFAULT_WD_LLM_TEMPERATURE
        if KEY_WD_LLM_NUM_PREDICT not in data:
            data[KEY_WD_LLM_NUM_PREDICT] = DEFAULT_WD_LLM_NUM_PREDICT
        if KEY_RL_LLM_TEMPERATURE not in data:
            data[KEY_RL_LLM_TEMPERATURE] = DEFAULT_RL_LLM_TEMPERATURE
        if KEY_RL_LLM_NUM_PREDICT not in data:
            data[KEY_RL_LLM_NUM_PREDICT] = DEFAULT_RL_LLM_NUM_PREDICT

        if KEY_CHAT_HISTORY_DIR not in data:
            data[KEY_CHAT_HISTORY_DIR] = _default_chat_history_dir()
        if KEY_RAG_INDEX_DATA_DIR not in data:
            data[KEY_RAG_INDEX_DATA_DIR] = DEFAULT_RAG_INDEX_DATA_DIR
        if KEY_MYDATA_DIR not in data:
            data[KEY_MYDATA_DIR] = DEFAULT_MYDATA_DIR
        if KEY_RAG_OFFLINE not in data:
            data[KEY_RAG_OFFLINE] = DEFAULT_RAG_OFFLINE
        if KEY_RAG_TOP_K not in data:
            data[KEY_RAG_TOP_K] = DEFAULT_RAG_TOP_K
        if KEY_WORKFLOW_DESIGNER_RAG_TOP_K not in data:
            data[KEY_WORKFLOW_DESIGNER_RAG_TOP_K] = DEFAULT_WORKFLOW_DESIGNER_RAG_TOP_K
        if KEY_RAG_MIN_SCORE not in data:
            data[KEY_RAG_MIN_SCORE] = DEFAULT_RAG_MIN_SCORE
        if KEY_RAG_FORMAT_MAX_CHARS not in data:
            data[KEY_RAG_FORMAT_MAX_CHARS] = DEFAULT_RAG_FORMAT_MAX_CHARS
        if KEY_RAG_FORMAT_SNIPPET_MAX not in data:
            data[KEY_RAG_FORMAT_SNIPPET_MAX] = DEFAULT_RAG_FORMAT_SNIPPET_MAX
        if KEY_READ_FILE_RAG_MAX_CHARS not in data:
            data[KEY_READ_FILE_RAG_MAX_CHARS] = DEFAULT_READ_FILE_RAG_MAX_CHARS
        if KEY_READ_FILE_RAG_SNIPPET_MAX not in data:
            data[KEY_READ_FILE_RAG_SNIPPET_MAX] = DEFAULT_READ_FILE_RAG_SNIPPET_MAX
        if KEY_CODING_IS_ALLOWED not in data:
            data[KEY_CODING_IS_ALLOWED] = DEFAULT_CODING_IS_ALLOWED
            added_coding_is_allowed = True
        if KEY_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS not in data:
            data[KEY_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS] = DEFAULT_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS
        if KEY_WORKFLOW_UNDO_MAX_DEPTH not in data:
            data[KEY_WORKFLOW_UNDO_MAX_DEPTH] = DEFAULT_WORKFLOW_UNDO_MAX_DEPTH
        if KEY_CHAT_STREAM_UI_INTERVAL_MS not in data:
            data[KEY_CHAT_STREAM_UI_INTERVAL_MS] = DEFAULT_CHAT_STREAM_UI_INTERVAL_MS
        if KEY_WEB_SEARCH_WORKFLOW_PATH not in data:
            data[KEY_WEB_SEARCH_WORKFLOW_PATH] = DEFAULT_WEB_SEARCH_WORKFLOW_PATH
        if KEY_BROWSER_WORKFLOW_PATH not in data:
            data[KEY_BROWSER_WORKFLOW_PATH] = DEFAULT_BROWSER_WORKFLOW_PATH
        if KEY_GITHUB_GET_WORKFLOW_PATH not in data:
            data[KEY_GITHUB_GET_WORKFLOW_PATH] = DEFAULT_GITHUB_GET_WORKFLOW_PATH
        migrated_rag_workflows = False
        if KEY_RAG_CONTEXT_WORKFLOW_PATH not in data:
            data[KEY_RAG_CONTEXT_WORKFLOW_PATH] = DEFAULT_RAG_CONTEXT_WORKFLOW_PATH
        elif data.get(KEY_RAG_CONTEXT_WORKFLOW_PATH) == "assistants/rag_context_workflow.json":
            data[KEY_RAG_CONTEXT_WORKFLOW_PATH] = DEFAULT_RAG_CONTEXT_WORKFLOW_PATH
            migrated_rag_workflows = True
        if KEY_RAG_UPDATE_WORKFLOW_PATH not in data:
            data[KEY_RAG_UPDATE_WORKFLOW_PATH] = DEFAULT_RAG_UPDATE_WORKFLOW_PATH
        elif data.get(KEY_RAG_UPDATE_WORKFLOW_PATH) == "assistants/rag_update.json":
            data[KEY_RAG_UPDATE_WORKFLOW_PATH] = DEFAULT_RAG_UPDATE_WORKFLOW_PATH
            migrated_rag_workflows = True
        if KEY_CREATE_FILENAME_WORKFLOW_PATH not in data:
            data[KEY_CREATE_FILENAME_WORKFLOW_PATH] = DEFAULT_CREATE_FILENAME_WORKFLOW_PATH
        if KEY_CREATE_FILENAME_PROMPT_PATH not in data:
            data[KEY_CREATE_FILENAME_PROMPT_PATH] = DEFAULT_CREATE_FILENAME_PROMPT_PATH
        if migrated_rag_workflows:
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
        if KEY_RAG_EMBEDDING_MODEL not in data:
            data[KEY_RAG_EMBEDDING_MODEL] = DEFAULT_RAG_EMBEDDING_MODEL
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
    workflow_designer_max_follow_ups: int | None = None,
    workflow_undo_max_depth: int | None = None,
    chat_stream_ui_interval_ms: int | None = None,
    debug_log_path: str | None = None,
    web_search_workflow_path: str | None = None,
    browser_workflow_path: str | None = None,
    rag_context_workflow_path: str | None = None,
    rag_update_workflow_path: str | None = None,
    create_filename_workflow_path: str | None = None,
    workflow_designer_prompt_path: str | None = None,
    rl_coach_prompt_path: str | None = None,
    create_filename_prompt_path: str | None = None,
    training_config_path: str | None = None,
    best_model_path: str | None = None,
    window_width: int | None = None,
    window_height: int | None = None,
) -> None:
    """Write settings to config/app_settings.json (only provided fields are updated)."""
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
    # Per-assistant updates
    if workflow_designer_llm_provider is not None:
        data[KEY_WD_LLM_PROVIDER] = (workflow_designer_llm_provider or "").strip() or DEFAULT_LLM_PROVIDER
    if workflow_designer_llm_provider_config_json is not None:
        data[KEY_WD_LLM_PROVIDER_CONFIG_JSON] = (workflow_designer_llm_provider_config_json or "").strip()
    if workflow_designer_ollama_host is not None:
        data[KEY_WD_OLLAMA_HOST] = (workflow_designer_ollama_host or "").strip() or DEFAULT_OLLAMA_HOST
    if workflow_designer_ollama_model is not None:
        data[KEY_WD_OLLAMA_MODEL] = (workflow_designer_ollama_model or "").strip() or DEFAULT_OLLAMA_MODEL

    if rl_coach_llm_provider is not None:
        data[KEY_RL_LLM_PROVIDER] = (rl_coach_llm_provider or "").strip() or DEFAULT_LLM_PROVIDER
    if rl_coach_llm_provider_config_json is not None:
        data[KEY_RL_LLM_PROVIDER_CONFIG_JSON] = (rl_coach_llm_provider_config_json or "").strip()
    if rl_coach_ollama_host is not None:
        data[KEY_RL_OLLAMA_HOST] = (rl_coach_ollama_host or "").strip() or DEFAULT_OLLAMA_HOST
    if rl_coach_ollama_model is not None:
        data[KEY_RL_OLLAMA_MODEL] = (rl_coach_ollama_model or "").strip() or DEFAULT_OLLAMA_MODEL

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
    if rag_embedding_model is not None:
        data[KEY_RAG_EMBEDDING_MODEL] = (rag_embedding_model or "").strip() or DEFAULT_RAG_EMBEDDING_MODEL
    if rag_offline is not None:
        data[KEY_RAG_OFFLINE] = bool(rag_offline)
    if coding_is_allowed is not None:
        data[KEY_CODING_IS_ALLOWED] = bool(coding_is_allowed)
    if workflow_designer_max_follow_ups is not None:
        try:
            n = int(workflow_designer_max_follow_ups)
        except (TypeError, ValueError):
            n = DEFAULT_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS
        data[KEY_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS] = max(
            MIN_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS,
            min(MAX_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS, n),
        )
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
    if web_search_workflow_path is not None:
        data[KEY_WEB_SEARCH_WORKFLOW_PATH] = (web_search_workflow_path or "").strip() or DEFAULT_WEB_SEARCH_WORKFLOW_PATH
    if browser_workflow_path is not None:
        data[KEY_BROWSER_WORKFLOW_PATH] = (browser_workflow_path or "").strip() or DEFAULT_BROWSER_WORKFLOW_PATH
    if rag_context_workflow_path is not None:
        data[KEY_RAG_CONTEXT_WORKFLOW_PATH] = (rag_context_workflow_path or "").strip() or DEFAULT_RAG_CONTEXT_WORKFLOW_PATH
    if rag_update_workflow_path is not None:
        data[KEY_RAG_UPDATE_WORKFLOW_PATH] = (rag_update_workflow_path or "").strip() or DEFAULT_RAG_UPDATE_WORKFLOW_PATH
    if create_filename_workflow_path is not None:
        data[KEY_CREATE_FILENAME_WORKFLOW_PATH] = (create_filename_workflow_path or "").strip() or DEFAULT_CREATE_FILENAME_WORKFLOW_PATH
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
    SETTINGS_PATH.write_text(json.dumps(data, indent=2), encoding="utf-8")

    # Ensure dirs exist (best effort)
    try:
        _resolve_dir(str(data.get(KEY_CHAT_HISTORY_DIR) or _default_chat_history_dir())).mkdir(parents=True, exist_ok=True)
    except OSError:
        pass


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


def get_web_search_workflow_path() -> Path:
    """Return the path to web_search.json (from app settings)."""
    raw = load_settings().get(KEY_WEB_SEARCH_WORKFLOW_PATH) or DEFAULT_WEB_SEARCH_WORKFLOW_PATH
    return _resolve_workflow_path(raw, DEFAULT_WEB_SEARCH_WORKFLOW_PATH)


def get_browser_workflow_path() -> Path:
    """Return the path to browser.json (from app settings)."""
    raw = load_settings().get(KEY_BROWSER_WORKFLOW_PATH) or DEFAULT_BROWSER_WORKFLOW_PATH
    return _resolve_workflow_path(raw, DEFAULT_BROWSER_WORKFLOW_PATH)


def get_github_get_workflow_path() -> Path:
    """Return the path to github_get.json (from app settings)."""
    raw = load_settings().get(KEY_GITHUB_GET_WORKFLOW_PATH) or DEFAULT_GITHUB_GET_WORKFLOW_PATH
    return _resolve_workflow_path(raw, DEFAULT_GITHUB_GET_WORKFLOW_PATH)


def get_rag_context_workflow_path() -> Path:
    """Return the path to rag_context_workflow.json (rag_search -> rag_filter, from app settings)."""
    raw = load_settings().get(KEY_RAG_CONTEXT_WORKFLOW_PATH) or DEFAULT_RAG_CONTEXT_WORKFLOW_PATH
    return _resolve_workflow_path(raw, DEFAULT_RAG_CONTEXT_WORKFLOW_PATH)


def get_rag_update_workflow_path() -> Path:
    """Return the path to rag_update.json (RagUpdate unit, from app settings)."""
    raw = load_settings().get(KEY_RAG_UPDATE_WORKFLOW_PATH) or DEFAULT_RAG_UPDATE_WORKFLOW_PATH
    return _resolve_workflow_path(raw, DEFAULT_RAG_UPDATE_WORKFLOW_PATH)


def get_doc_to_text_workflow_path() -> Path:
    """Return the path to doc_to_text.json (Inject → LoadDocument → TablesToText → Aggregate → Prompt)."""
    raw = load_settings().get("doc_to_text_workflow_path") or DEFAULT_DOC_TO_TEXT_WORKFLOW_PATH
    return _resolve_workflow_path(raw, DEFAULT_DOC_TO_TEXT_WORKFLOW_PATH)


def get_workflow_designer_prompt_path() -> Path:
    """Return the path to the Workflow Designer prompt template (from app settings)."""
    raw = load_settings().get(KEY_WORKFLOW_DESIGNER_PROMPT_PATH) or DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH
    return _resolve_workflow_path(raw, DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH)


def get_rl_coach_prompt_path() -> Path:
    """Return the path to the RL Coach prompt template (from app settings)."""
    raw = load_settings().get(KEY_RL_COACH_PROMPT_PATH) or DEFAULT_RL_COACH_PROMPT_PATH
    return _resolve_workflow_path(raw, DEFAULT_RL_COACH_PROMPT_PATH)


def get_create_filename_workflow_path() -> Path:
    """Return the path to create_filename.json workflow (from app settings)."""
    raw = load_settings().get(KEY_CREATE_FILENAME_WORKFLOW_PATH) or DEFAULT_CREATE_FILENAME_WORKFLOW_PATH
    norm = str(raw).strip().replace("\\", "/")
    if norm == "assistants/create_filename.json":
        raw = DEFAULT_CREATE_FILENAME_WORKFLOW_PATH
    return _resolve_workflow_path(raw, DEFAULT_CREATE_FILENAME_WORKFLOW_PATH)


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
    assistant: 'workflow_designer' | 'rl_coach'
    """
    data = load_settings()
    a = (assistant or "").strip().lower()
    if a == "rl_coach":
        return (data.get(KEY_RL_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER).strip() or DEFAULT_LLM_PROVIDER
    return (data.get(KEY_WD_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER).strip() or DEFAULT_LLM_PROVIDER


def get_llm_provider_config(*, assistant: str) -> dict:
    """
    Return provider config dict passed into `LLM_integrations.client.chat`.
    If config JSON is empty and provider=='ollama', derive from assistant-specific ollama_host/ollama_model.
    """
    data = load_settings()
    a = (assistant or "").strip().lower()
    if a == "rl_coach":
        prov = (data.get(KEY_RL_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER).strip() or DEFAULT_LLM_PROVIDER
        raw = (data.get(KEY_RL_LLM_PROVIDER_CONFIG_JSON) or "").strip()
        ollama_host = (data.get(KEY_RL_OLLAMA_HOST) or data.get(KEY_WD_OLLAMA_HOST) or _default_ollama_host()).strip()
        ollama_model = (data.get(KEY_RL_OLLAMA_MODEL) or data.get(KEY_WD_OLLAMA_MODEL) or _default_ollama_model()).strip()
    else:
        prov = (data.get(KEY_WD_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER).strip() or DEFAULT_LLM_PROVIDER
        raw = (data.get(KEY_WD_LLM_PROVIDER_CONFIG_JSON) or "").strip()
        ollama_host = (data.get(KEY_WD_OLLAMA_HOST) or data.get(KEY_OLLAMA_HOST) or _default_ollama_host()).strip()
        ollama_model = (data.get(KEY_WD_OLLAMA_MODEL) or data.get(KEY_OLLAMA_MODEL) or _default_ollama_model()).strip()

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
    raw = load_settings().get(KEY_RAG_INDEX_DATA_DIR) or DEFAULT_RAG_INDEX_DATA_DIR
    path = _resolve_dir(str(raw))
    path.mkdir(parents=True, exist_ok=True)
    return path


def get_mydata_dir() -> Path:
    """Return resolved directory for mydata content (workflows, nodes, docs) to be indexed. No index files here."""
    raw = load_settings().get(KEY_MYDATA_DIR) or DEFAULT_MYDATA_DIR
    return _resolve_dir(str(raw))


def get_rag_embedding_model() -> str:
    """Return the embedding model name for RAG (sentence-transformers)."""
    return (load_settings().get(KEY_RAG_EMBEDDING_MODEL) or DEFAULT_RAG_EMBEDDING_MODEL).strip()


def get_rag_offline() -> bool:
    """When True, RAG uses only cached embedding model (HF_HUB_OFFLINE=1). One-time download when unchecked."""
    return bool(load_settings().get(KEY_RAG_OFFLINE, DEFAULT_RAG_OFFLINE))


def get_rag_top_k() -> int:
    """Default RagSearch top_k for RL Coach / non–Workflow Designer RAG context."""
    raw = load_settings().get(KEY_RAG_TOP_K, DEFAULT_RAG_TOP_K)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_RAG_TOP_K
    return max(1, min(50, n))


def get_workflow_designer_rag_top_k() -> int:
    """RagSearch top_k when assistant is Workflow Designer (tighter context)."""
    raw = load_settings().get(KEY_WORKFLOW_DESIGNER_RAG_TOP_K, DEFAULT_WORKFLOW_DESIGNER_RAG_TOP_K)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_WORKFLOW_DESIGNER_RAG_TOP_K
    return max(1, min(50, n))


def get_rag_min_score() -> float:
    """Minimum similarity score (rag_filter on column score, op ge). Clamped 0–1."""
    raw = load_settings().get(KEY_RAG_MIN_SCORE, DEFAULT_RAG_MIN_SCORE)
    try:
        x = float(raw)
    except (TypeError, ValueError):
        x = DEFAULT_RAG_MIN_SCORE
    return max(0.0, min(1.0, x))


def get_rag_format_max_chars() -> int:
    """FormatRagPrompt max total chars for query-based RAG context."""
    raw = load_settings().get(KEY_RAG_FORMAT_MAX_CHARS, DEFAULT_RAG_FORMAT_MAX_CHARS)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_RAG_FORMAT_MAX_CHARS
    return max(1, min(5000, n))


def get_rag_format_snippet_max() -> int:
    """FormatRagPrompt per-snippet cap for query-based RAG context."""
    raw = load_settings().get(KEY_RAG_FORMAT_SNIPPET_MAX, DEFAULT_RAG_FORMAT_SNIPPET_MAX)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_RAG_FORMAT_SNIPPET_MAX
    return max(1, min(2000, int(n)))


def get_read_file_rag_max_chars() -> int:
    """FormatRagPrompt max_chars for read_file / path-based RAG retrieval."""
    raw = load_settings().get(KEY_READ_FILE_RAG_MAX_CHARS, DEFAULT_READ_FILE_RAG_MAX_CHARS)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_READ_FILE_RAG_MAX_CHARS
    return max(1, min(5000, n))


def get_read_file_rag_snippet_max() -> int:
    """FormatRagPrompt snippet_max for read_file / path-based RAG retrieval."""
    raw = load_settings().get(KEY_READ_FILE_RAG_SNIPPET_MAX, DEFAULT_READ_FILE_RAG_SNIPPET_MAX)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_READ_FILE_RAG_SNIPPET_MAX
    return max(1, min(5000, n))


def get_coding_is_allowed() -> bool:
    """When True, Workflow Designer shows add_code_block and allows custom code on function units."""
    return bool(load_settings().get(KEY_CODING_IS_ALLOWED, DEFAULT_CODING_IS_ALLOWED))


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
    data = load_settings()
    return _coerce_llm_generation_options(
        data.get(KEY_WD_LLM_TEMPERATURE, DEFAULT_WD_LLM_TEMPERATURE),
        data.get(KEY_WD_LLM_NUM_PREDICT, DEFAULT_WD_LLM_NUM_PREDICT),
        default_temperature=DEFAULT_WD_LLM_TEMPERATURE,
        default_num_predict=DEFAULT_WD_LLM_NUM_PREDICT,
    )


def get_rl_coach_llm_generation_options() -> dict[str, Any]:
    """Ollama options for RL Coach workflow LLMAgent."""
    data = load_settings()
    return _coerce_llm_generation_options(
        data.get(KEY_RL_LLM_TEMPERATURE, DEFAULT_RL_LLM_TEMPERATURE),
        data.get(KEY_RL_LLM_NUM_PREDICT, DEFAULT_RL_LLM_NUM_PREDICT),
        default_temperature=DEFAULT_RL_LLM_TEMPERATURE,
        default_num_predict=DEFAULT_RL_LLM_NUM_PREDICT,
    )


def get_workflow_designer_max_follow_ups() -> int:
    """Max parser/tool follow-up iterations and post-apply review rounds for Workflow Designer chat."""
    raw = load_settings().get(KEY_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS, DEFAULT_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS)
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS
    return max(MIN_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS, min(MAX_WORKFLOW_DESIGNER_MAX_FOLLOW_UPS, n))


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


def build_settings_tab(
    page: ft.Page,
    *,
    on_saved: Callable[[], None] | None = None,
) -> ft.Control:
    """
    Build the Settings tab content: workflow project name + workflow save path template.
    on_saved: optional callback called when user saves.
    """
    initial = load_settings()
    project_value = initial.get(KEY_WORKFLOW_PROJECT_NAME) or _default_project_name()
    template_value = initial.get(KEY_WORKFLOW_SAVE_PATH_TEMPLATE) or _default_workflow_save_path_template()
    training_config_path_value = initial.get(KEY_TRAINING_CONFIG_PATH) or DEFAULT_TRAINING_CONFIG_PATH
    best_model_path_value = (initial.get(KEY_BEST_MODEL_PATH) or "").strip()
    wd_provider_value = initial.get(KEY_WD_LLM_PROVIDER) or initial.get(KEY_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER
    wd_provider_cfg_value = initial.get(KEY_WD_LLM_PROVIDER_CONFIG_JSON) or initial.get(KEY_LLM_PROVIDER_CONFIG_JSON) or DEFAULT_LLM_PROVIDER_CONFIG_JSON
    wd_ollama_host_value = initial.get(KEY_WD_OLLAMA_HOST) or initial.get(KEY_OLLAMA_HOST) or DEFAULT_OLLAMA_HOST
    wd_ollama_model_value = initial.get(KEY_WD_OLLAMA_MODEL) or initial.get(KEY_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL

    rl_provider_value = initial.get(KEY_RL_LLM_PROVIDER) or wd_provider_value
    rl_provider_cfg_value = initial.get(KEY_RL_LLM_PROVIDER_CONFIG_JSON) or wd_provider_cfg_value
    rl_ollama_host_value = initial.get(KEY_RL_OLLAMA_HOST) or wd_ollama_host_value
    rl_ollama_model_value = initial.get(KEY_RL_OLLAMA_MODEL) or wd_ollama_model_value

    ollama_api_key_value = (initial.get(KEY_OLLAMA_API_KEY) or "").strip()
    start_ollama_with_app_value = bool(initial.get(KEY_START_OLLAMA_WITH_APP, False))
    ollama_executable_path_value = (initial.get(KEY_OLLAMA_EXECUTABLE_PATH) or "").strip()
    chat_history_dir_value = initial.get(KEY_CHAT_HISTORY_DIR) or _default_chat_history_dir()
    mydata_dir_value = initial.get(KEY_MYDATA_DIR) or DEFAULT_MYDATA_DIR
    rag_embedding_model_value = initial.get(KEY_RAG_EMBEDDING_MODEL) or DEFAULT_RAG_EMBEDDING_MODEL
    rag_offline_value = bool(initial.get(KEY_RAG_OFFLINE, DEFAULT_RAG_OFFLINE))
    coding_is_allowed_value = bool(initial.get(KEY_CODING_IS_ALLOWED, DEFAULT_CODING_IS_ALLOWED))
    workflow_undo_max_depth_value = get_workflow_undo_max_depth()
    chat_stream_ui_interval_ms_value = get_chat_stream_ui_interval_ms()
    debug_log_path_value = initial.get(KEY_DEBUG_LOG_PATH) or DEFAULT_DEBUG_LOG_PATH
    create_filename_workflow_path_value = initial.get(KEY_CREATE_FILENAME_WORKFLOW_PATH) or DEFAULT_CREATE_FILENAME_WORKFLOW_PATH
    workflow_designer_prompt_path_value = initial.get(KEY_WORKFLOW_DESIGNER_PROMPT_PATH) or DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH
    rl_coach_prompt_path_value = initial.get(KEY_RL_COACH_PROMPT_PATH) or DEFAULT_RL_COACH_PROMPT_PATH
    create_filename_prompt_path_value = initial.get(KEY_CREATE_FILENAME_PROMPT_PATH) or DEFAULT_CREATE_FILENAME_PROMPT_PATH

    project_field = ft.TextField(
        label="Workflow project name",
        value=project_value,
        hint_text="e.g. temperature_control",
        width=400,
    )
    template_field = ft.TextField(
        label="Workflow save path template",
        value=template_value,
        hint_text="e.g. config/my_workflows/$PROJECT_NAME$/$PROJECT_NAME$_workflow_$YY-MM-DD-HHMMSS$.json",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    training_config_path_field = ft.TextField(
        label="Training config path (last used)",
        value=training_config_path_value,
        hint_text="e.g. config/examples/training_config.yaml (relative to repo root)",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    best_model_path_field = ft.TextField(
        label="Best model path",
        value=best_model_path_value,
        hint_text="e.g. models/temperature-control-agent/best/ or path to best_model.zip",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    create_filename_workflow_path_field = ft.TextField(
        label="Create filename workflow path",
        value=create_filename_workflow_path_value,
        hint_text="e.g. assistants/roles/chat_name_creator/create_filename.json",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    workflow_designer_prompt_path_field = ft.TextField(
        label="Workflow Designer prompt path",
        value=workflow_designer_prompt_path_value,
        hint_text="e.g. config/prompts/workflow_designer.json",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    rl_coach_prompt_path_field = ft.TextField(
        label="RL Coach prompt path",
        value=rl_coach_prompt_path_value,
        hint_text="e.g. config/prompts/rl_coach.json",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    create_filename_prompt_path_field = ft.TextField(
        label="Create filename prompt path",
        value=create_filename_prompt_path_value,
        hint_text="e.g. config/prompts/create_filename.json",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    wd_llm_provider_dd = ft.Dropdown(
        label="Workflow Designer: LLM provider",
        value=str(wd_provider_value),
        width=220,
        height=36,
        text_style=ft.TextStyle(size=12),
        options=[ft.dropdown.Option(p) for p in list_llm_providers()],
    )
    wd_llm_provider_config_field = ft.TextField(
        label="Workflow Designer: provider config (JSON, optional)",
        value=str(wd_provider_cfg_value),
        hint_text='e.g. {"host":"http://127.0.0.1:11434","model":"llama3.2"}',
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
        multiline=True,
        min_lines=2,
        max_lines=6,
    )
    wd_ollama_host_field = ft.TextField(
        label="Workflow Designer: Ollama server (host:port)",
        value=wd_ollama_host_value,
        hint_text="e.g. http://127.0.0.1:11434",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    wd_ollama_model_field = ft.TextField(
        label="Workflow Designer: Ollama model",
        value=wd_ollama_model_value,
        hint_text="e.g. llama3.2 or qwen3-coder:480b-cloud for Cloud",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    ollama_api_key_field = ft.TextField(
        label="Ollama API key (optional, for Cloud)",
        value=ollama_api_key_value,
        password=True,
        can_reveal_password=True,
        hint_text="From ollama.com/settings/keys; or set OLLAMA_API_KEY env",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    start_ollama_with_app_cb = ft.Checkbox(
        label="Start Ollama server with app (no need to run 'ollama serve' separately)",
        value=start_ollama_with_app_value,
    )
    ollama_executable_path_field = ft.TextField(
        label="Ollama executable path (optional)",
        value=ollama_executable_path_value,
        hint_text="Leave blank to use 'ollama' from PATH",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )

    rl_llm_provider_dd = ft.Dropdown(
        label="RL Coach: LLM provider",
        value=str(rl_provider_value),
        width=220,
        height=36,
        text_style=ft.TextStyle(size=12),
        options=[ft.dropdown.Option(p) for p in list_llm_providers()],
    )
    rl_llm_provider_config_field = ft.TextField(
        label="RL Coach: provider config (JSON, optional)",
        value=str(rl_provider_cfg_value),
        hint_text='e.g. {"host":"http://127.0.0.1:11434","model":"llama3.2"}',
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
        multiline=True,
        min_lines=2,
        max_lines=6,
    )
    rl_ollama_host_field = ft.TextField(
        label="RL Coach: Ollama server (host:port)",
        value=rl_ollama_host_value,
        hint_text="e.g. http://127.0.0.1:11434",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    rl_ollama_model_field = ft.TextField(
        label="RL Coach: Ollama model",
        value=rl_ollama_model_value,
        hint_text="e.g. llama3.2",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    chat_history_dir_field = ft.TextField(
        label="Chat history directory",
        value=chat_history_dir_value,
        hint_text="e.g. mydata/chat_history (relative to repo) or /abs/path/...",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    mydata_dir_field = ft.TextField(
        label="Mydata directory (content to index)",
        value=mydata_dir_value,
        hint_text="e.g. mydata (relative to repo). Index data (chroma_db, state) is in rag/.rag_index_data/",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    RAG_EMBEDDING_OPTIONS = [
        "sentence-transformers/all-MiniLM-L6-v2",
        "BAAI/bge-small-en-v1.5",
        "sentence-transformers/all-mpnet-base-v2",
        "intfloat/e5-small-v2",
        "BAAI/bge-base-en-v1.5",
    ]
    options = list(RAG_EMBEDDING_OPTIONS)
    if rag_embedding_model_value and rag_embedding_model_value not in options:
        options.insert(0, rag_embedding_model_value)
    rag_embedding_model_dd = ft.Dropdown(
        label="RAG embedding model",
        value=rag_embedding_model_value,
        width=400,
        height=36,
        text_style=ft.TextStyle(font_family="monospace", size=12),
        options=[ft.dropdown.Option(m) for m in options],
    )
    rag_offline_cb = ft.Checkbox(
        label="Use RAG offline (use cached model only; one-time download when unchecked)",
        value=rag_offline_value,
    )
    coding_is_allowed_cb = ft.Checkbox(
        label="Workflow Designer: allow custom code (add_code_block on function units). When off, only use units from the Units Library.",
        value=coding_is_allowed_value,
    )
    workflow_undo_max_depth_field = ft.TextField(
        label="Workflow undo max depth",
        value=str(workflow_undo_max_depth_value),
        hint_text=f"{MIN_WORKFLOW_UNDO_MAX_DEPTH}..{MAX_WORKFLOW_UNDO_MAX_DEPTH}",
        width=220,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    chat_stream_ui_interval_ms_field = ft.TextField(
        label="Chat stream UI interval (ms)",
        value=str(chat_stream_ui_interval_ms_value),
        hint_text=f"{MIN_CHAT_STREAM_UI_INTERVAL_MS}..{MAX_CHAT_STREAM_UI_INTERVAL_MS}",
        width=220,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )
    debug_log_path_field = ft.TextField(
        label="Run console: log file path (grep after run)",
        value=debug_log_path_value,
        hint_text="e.g. err.txt or log.txt (relative to repo). Debug units write here; grep runs on this file after workflow run.",
        width=400,
        text_style=ft.TextStyle(font_family="monospace", size=12),
    )

    def _on_build_prompts_click(pg: ft.Page) -> None:
        async def _run() -> None:
            try:
                import sys
                if str(REPO_ROOT) not in sys.path:
                    sys.path.insert(0, str(REPO_ROOT))
                from scripts.write_prompt_templates import build_prompt_templates
            except ImportError as err:
                pg.snack_bar = ft.SnackBar(content=ft.Text(f"Build prompts: {err}"), open=True)
                pg.update()
                return
            success, message = await asyncio.to_thread(build_prompt_templates, None, None)
            if success:
                await show_toast(pg, "Built successfully")
            else:
                pg.snack_bar = ft.SnackBar(
                    content=ft.Text(f"Build prompts failed: {message}"),
                    open=True,
                )
            pg.update()

        pg.run_task(_run)

    def save_click(_e: ft.ControlEvent) -> None:
        new_project = (project_field.value or "").strip() or _default_project_name()
        new_template = (template_field.value or "").strip() or _default_workflow_save_path_template()
        new_training_config_path = (training_config_path_field.value or "").strip() or DEFAULT_TRAINING_CONFIG_PATH
        new_best_model_path = (best_model_path_field.value or "").strip()
        wd_provider = (wd_llm_provider_dd.value or "").strip() or DEFAULT_LLM_PROVIDER
        wd_provider_cfg = (wd_llm_provider_config_field.value or "").strip()
        wd_host = (wd_ollama_host_field.value or "").strip() or DEFAULT_OLLAMA_HOST
        wd_model = (wd_ollama_model_field.value or "").strip() or DEFAULT_OLLAMA_MODEL
        ollama_api_key = (ollama_api_key_field.value or "").strip()
        start_ollama = bool(start_ollama_with_app_cb.value)
        ollama_path = (ollama_executable_path_field.value or "").strip()

        rl_provider = (rl_llm_provider_dd.value or "").strip() or DEFAULT_LLM_PROVIDER
        rl_provider_cfg = (rl_llm_provider_config_field.value or "").strip()
        rl_host = (rl_ollama_host_field.value or "").strip() or DEFAULT_OLLAMA_HOST
        rl_model = (rl_ollama_model_field.value or "").strip() or DEFAULT_OLLAMA_MODEL

        new_chat_dir = (chat_history_dir_field.value or "").strip() or _default_chat_history_dir()
        new_mydata_dir = (mydata_dir_field.value or "").strip() or DEFAULT_MYDATA_DIR
        new_rag_model = (rag_embedding_model_dd.value or "").strip() or DEFAULT_RAG_EMBEDDING_MODEL
        new_rag_offline = bool(rag_offline_cb.value)
        new_coding_is_allowed = bool(coding_is_allowed_cb.value)
        try:
            new_workflow_undo_max_depth = int((workflow_undo_max_depth_field.value or "").strip())
        except (TypeError, ValueError):
            new_workflow_undo_max_depth = DEFAULT_WORKFLOW_UNDO_MAX_DEPTH
        try:
            new_chat_stream_ui_interval_ms = int((chat_stream_ui_interval_ms_field.value or "").strip())
        except (TypeError, ValueError):
            new_chat_stream_ui_interval_ms = DEFAULT_CHAT_STREAM_UI_INTERVAL_MS
        new_debug_log_path = (debug_log_path_field.value or "").strip() or DEFAULT_DEBUG_LOG_PATH
        new_create_filename_workflow_path = (create_filename_workflow_path_field.value or "").strip() or DEFAULT_CREATE_FILENAME_WORKFLOW_PATH
        new_workflow_designer_prompt_path = (workflow_designer_prompt_path_field.value or "").strip() or DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH
        new_rl_coach_prompt_path = (rl_coach_prompt_path_field.value or "").strip() or DEFAULT_RL_COACH_PROMPT_PATH
        new_create_filename_prompt_path = (create_filename_prompt_path_field.value or "").strip() or DEFAULT_CREATE_FILENAME_PROMPT_PATH
        try:
            save_settings(
                workflow_project_name=new_project,
                workflow_save_path_template=new_template,
                training_config_path=new_training_config_path,
                best_model_path=new_best_model_path,
                create_filename_workflow_path=new_create_filename_workflow_path,
                workflow_designer_prompt_path=new_workflow_designer_prompt_path,
                rl_coach_prompt_path=new_rl_coach_prompt_path,
                create_filename_prompt_path=new_create_filename_prompt_path,
                workflow_designer_llm_provider=wd_provider,
                workflow_designer_llm_provider_config_json=wd_provider_cfg,
                workflow_designer_ollama_host=wd_host,
                workflow_designer_ollama_model=wd_model,
                ollama_api_key=ollama_api_key,
                start_ollama_with_app=start_ollama,
                ollama_executable_path=ollama_path,
                rl_coach_llm_provider=rl_provider,
                rl_coach_llm_provider_config_json=rl_provider_cfg,
                rl_coach_ollama_host=rl_host,
                rl_coach_ollama_model=rl_model,
                chat_history_dir=new_chat_dir,
                mydata_dir=new_mydata_dir,
                rag_embedding_model=new_rag_model,
                rag_offline=new_rag_offline,
                coding_is_allowed=new_coding_is_allowed,
                workflow_undo_max_depth=new_workflow_undo_max_depth,
                chat_stream_ui_interval_ms=new_chat_stream_ui_interval_ms,
                debug_log_path=new_debug_log_path,
            )
            project_field.value = new_project
            template_field.value = new_template
            training_config_path_field.value = new_training_config_path
            best_model_path_field.value = new_best_model_path
            create_filename_workflow_path_field.value = new_create_filename_workflow_path
            workflow_designer_prompt_path_field.value = new_workflow_designer_prompt_path
            rl_coach_prompt_path_field.value = new_rl_coach_prompt_path
            create_filename_prompt_path_field.value = new_create_filename_prompt_path
            wd_llm_provider_dd.value = wd_provider
            wd_llm_provider_config_field.value = wd_provider_cfg
            wd_ollama_host_field.value = wd_host
            wd_ollama_model_field.value = wd_model
            ollama_api_key_field.value = ollama_api_key
            start_ollama_with_app_cb.value = start_ollama
            ollama_executable_path_field.value = ollama_path

            rl_llm_provider_dd.value = rl_provider
            rl_llm_provider_config_field.value = rl_provider_cfg
            rl_ollama_host_field.value = rl_host
            rl_ollama_model_field.value = rl_model

            chat_history_dir_field.value = new_chat_dir
            mydata_dir_field.value = new_mydata_dir
            rag_embedding_model_dd.value = new_rag_model
            rag_offline_cb.value = new_rag_offline
            workflow_undo_max_depth_field.value = str(
                max(
                    MIN_WORKFLOW_UNDO_MAX_DEPTH,
                    min(MAX_WORKFLOW_UNDO_MAX_DEPTH, new_workflow_undo_max_depth),
                )
            )
            chat_stream_ui_interval_ms_field.value = str(
                max(
                    MIN_CHAT_STREAM_UI_INTERVAL_MS,
                    min(MAX_CHAT_STREAM_UI_INTERVAL_MS, new_chat_stream_ui_interval_ms),
                )
            )
            project_field.update()
            template_field.update()
            training_config_path_field.update()
            best_model_path_field.update()
            create_filename_workflow_path_field.update()
            workflow_designer_prompt_path_field.update()
            rl_coach_prompt_path_field.update()
            create_filename_prompt_path_field.update()
            wd_llm_provider_dd.update()
            wd_llm_provider_config_field.update()
            wd_ollama_host_field.update()
            wd_ollama_model_field.update()
            ollama_api_key_field.update()
            start_ollama_with_app_cb.update()
            ollama_executable_path_field.update()
            rl_llm_provider_dd.update()
            rl_llm_provider_config_field.update()
            rl_ollama_host_field.update()
            rl_ollama_model_field.update()
            chat_history_dir_field.update()
            mydata_dir_field.update()
            rag_embedding_model_dd.update()
            rag_offline_cb.update()
            coding_is_allowed_cb.update()
            workflow_undo_max_depth_field.update()
            chat_stream_ui_interval_ms_field.update()
            debug_log_path_field.value = new_debug_log_path
            debug_log_path_field.update()
            if on_saved:
                on_saved()
            async def _show_saved_toast() -> None:
                await show_toast(page, "Saved")
            page.run_task(_show_saved_toast)
            page.update()
        except OSError as ex:
            page.snack_bar = ft.SnackBar(content=ft.Text(f"Could not save: {ex}"), open=True)
            page.update()

    return ft.Container(
        content=ft.Column(
            [
                ft.Text("Settings", size=20, weight=ft.FontWeight.BOLD),
                ft.Text(
                    "Workflow save settings (project name + versioned save path template). "
                    f"Stored in {SETTINGS_FILENAME} under config/.",
                    size=12,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=16),
                project_field,
                ft.Container(height=8),
                template_field,
                ft.Container(height=8),
                training_config_path_field,
                ft.Container(height=8),
                best_model_path_field,
                ft.Container(height=16),
                ft.Text("Workflow and prompt paths", size=14, weight=ft.FontWeight.W_600),
                ft.Text(
                    "Paths relative to repo root (except Workflow Designer / RL Coach main chat graphs: "
                    "set chat.workflow in assistants/roles/<role_id>/role.yaml). Used by chat, scripts, and editor.",
                    size=12,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=8),
                create_filename_workflow_path_field,
                ft.Container(height=8),
                workflow_designer_prompt_path_field,
                ft.Container(height=8),
                rl_coach_prompt_path_field,
                ft.Container(height=8),
                create_filename_prompt_path_field,
                ft.Container(height=8),
                ft.Text("Assistants / LLM", size=14, weight=ft.FontWeight.W_600),
                ft.Container(height=8),
                ft.Text("Workflow Designer", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_400),
                ft.Container(height=8),
                wd_llm_provider_dd,
                ft.Container(height=8),
                wd_llm_provider_config_field,
                ft.Container(height=8),
                wd_ollama_host_field,
                ft.Container(height=8),
                wd_ollama_model_field,
                ft.Container(height=8),
                ollama_api_key_field,
                ft.Container(height=8),
                start_ollama_with_app_cb,
                ft.Container(height=4),
                ollama_executable_path_field,
                ft.Container(height=16),
                ft.Text("RL Coach", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_400),
                ft.Container(height=8),
                rl_llm_provider_dd,
                ft.Container(height=8),
                rl_llm_provider_config_field,
                ft.Container(height=8),
                rl_ollama_host_field,
                ft.Container(height=8),
                rl_ollama_model_field,
                ft.Container(height=8),
                chat_history_dir_field,
                ft.Container(height=16),
                ft.Text("RAG", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_400),
                ft.Container(height=8),
                mydata_dir_field,
                ft.Container(height=8),
                rag_embedding_model_dd,
                ft.Container(height=8),
                rag_offline_cb,
                ft.Container(height=16),
                ft.Text("Workflow Designer: coding", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_400),
                ft.Container(height=8),
                coding_is_allowed_cb,
                ft.Container(height=8),
                workflow_undo_max_depth_field,
                ft.Container(height=8),
                chat_stream_ui_interval_ms_field,
                ft.Container(height=16),
                ft.Text("Run console: grep log after run", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_400),
                ft.Container(height=8),
                debug_log_path_field,
                ft.Container(height=16),
                ft.Text("Prompts", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_400),
                ft.Container(height=8),
                ft.ElevatedButton("Build prompts", on_click=lambda e: _on_build_prompts_click(page)),
                ft.Container(height=8),
                ft.ElevatedButton("Save", on_click=save_click),
            ],
            alignment=ft.MainAxisAlignment.START,
            horizontal_alignment=ft.CrossAxisAlignment.START,
            spacing=4,
            scroll=ft.ScrollMode.AUTO,
        ),
        padding=24,
        expand=True,
    )
