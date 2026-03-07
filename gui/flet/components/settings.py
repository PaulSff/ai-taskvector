"""
Settings tab: store app preferences (e.g. workflow save path) in config JSON.
Default workflow path template:
  config/my_workflows/$PROJECT_NAME$/$PROJECT_NAME$_workflow_$YY-MM-DD-HHMMSS$.json
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Callable

import flet as ft

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

KEY_LLM_PROVIDER = "llm_provider"  # legacy/global
DEFAULT_LLM_PROVIDER = "ollama"
KEY_LLM_PROVIDER_CONFIG_JSON = "llm_provider_config_json"  # legacy/global
DEFAULT_LLM_PROVIDER_CONFIG_JSON = ""

# Workflow Designer profile
KEY_WD_LLM_PROVIDER = "workflow_designer_llm_provider"
KEY_WD_LLM_PROVIDER_CONFIG_JSON = "workflow_designer_llm_provider_config_json"
KEY_WD_OLLAMA_HOST = "workflow_designer_ollama_host"
KEY_WD_OLLAMA_MODEL = "workflow_designer_ollama_model"

# RL Coach profile
KEY_RL_LLM_PROVIDER = "rl_coach_llm_provider"
KEY_RL_LLM_PROVIDER_CONFIG_JSON = "rl_coach_llm_provider_config_json"
KEY_RL_OLLAMA_HOST = "rl_coach_ollama_host"
KEY_RL_OLLAMA_MODEL = "rl_coach_ollama_model"

# Chat history persistence (assistants chat)
KEY_CHAT_HISTORY_DIR = "chat_history_dir"
DEFAULT_CHAT_HISTORY_DIR = "chat_history"

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
            # Per-assistant defaults
            KEY_WD_LLM_PROVIDER: DEFAULT_LLM_PROVIDER,
            KEY_WD_LLM_PROVIDER_CONFIG_JSON: DEFAULT_LLM_PROVIDER_CONFIG_JSON,
            KEY_WD_OLLAMA_HOST: DEFAULT_OLLAMA_HOST,
            KEY_WD_OLLAMA_MODEL: DEFAULT_OLLAMA_MODEL,
            KEY_RL_LLM_PROVIDER: DEFAULT_LLM_PROVIDER,
            KEY_RL_LLM_PROVIDER_CONFIG_JSON: DEFAULT_LLM_PROVIDER_CONFIG_JSON,
            KEY_RL_OLLAMA_HOST: DEFAULT_OLLAMA_HOST,
            KEY_RL_OLLAMA_MODEL: DEFAULT_OLLAMA_MODEL,
            KEY_CHAT_HISTORY_DIR: _default_chat_history_dir(),
            KEY_RAG_INDEX_DATA_DIR: DEFAULT_RAG_INDEX_DATA_DIR,
            KEY_MYDATA_DIR: DEFAULT_MYDATA_DIR,
            KEY_RAG_EMBEDDING_MODEL: DEFAULT_RAG_EMBEDDING_MODEL,
            KEY_RAG_OFFLINE: DEFAULT_RAG_OFFLINE,
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
        if KEY_WORKFLOW_PROJECT_NAME not in data:
            data[KEY_WORKFLOW_PROJECT_NAME] = _default_project_name()
        if KEY_WORKFLOW_SAVE_PATH_TEMPLATE not in data:
            data[KEY_WORKFLOW_SAVE_PATH_TEMPLATE] = _default_workflow_save_path_template()

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

        if KEY_CHAT_HISTORY_DIR not in data:
            data[KEY_CHAT_HISTORY_DIR] = _default_chat_history_dir()
        if KEY_RAG_INDEX_DATA_DIR not in data:
            data[KEY_RAG_INDEX_DATA_DIR] = DEFAULT_RAG_INDEX_DATA_DIR
        if KEY_MYDATA_DIR not in data:
            data[KEY_MYDATA_DIR] = DEFAULT_MYDATA_DIR
        if KEY_RAG_OFFLINE not in data:
            data[KEY_RAG_OFFLINE] = DEFAULT_RAG_OFFLINE
        if KEY_RAG_EMBEDDING_MODEL not in data:
            data[KEY_RAG_EMBEDDING_MODEL] = DEFAULT_RAG_EMBEDDING_MODEL
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
    ollama_host: str | None = None,
    ollama_model: str | None = None,
    chat_history_dir: str | None = None,
    mydata_dir: str | None = None,
    rag_embedding_model: str | None = None,
    rag_offline: bool | None = None,
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


def get_ollama_host() -> str:
    """Return Ollama host URL, e.g. http://127.0.0.1:11434"""
    return load_settings().get(KEY_OLLAMA_HOST) or DEFAULT_OLLAMA_HOST


def get_ollama_model() -> str:
    """Return Ollama model name to use for assistants chat."""
    return load_settings().get(KEY_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL


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
        ollama_host = (data.get(KEY_RL_OLLAMA_HOST) or data.get(KEY_WD_OLLAMA_HOST) or DEFAULT_OLLAMA_HOST).strip()
        ollama_model = (data.get(KEY_RL_OLLAMA_MODEL) or data.get(KEY_WD_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL).strip()
    else:
        prov = (data.get(KEY_WD_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER).strip() or DEFAULT_LLM_PROVIDER
        raw = (data.get(KEY_WD_LLM_PROVIDER_CONFIG_JSON) or "").strip()
        ollama_host = (data.get(KEY_WD_OLLAMA_HOST) or data.get(KEY_OLLAMA_HOST) or DEFAULT_OLLAMA_HOST).strip()
        ollama_model = (data.get(KEY_WD_OLLAMA_MODEL) or data.get(KEY_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL).strip()

    if raw:
        try:
            parsed = json.loads(raw)
            if isinstance(parsed, dict):
                return parsed
        except json.JSONDecodeError:
            pass
    if prov == "ollama":
        return {"host": ollama_host or DEFAULT_OLLAMA_HOST, "model": ollama_model or DEFAULT_OLLAMA_MODEL}
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
    wd_provider_value = initial.get(KEY_WD_LLM_PROVIDER) or initial.get(KEY_LLM_PROVIDER) or DEFAULT_LLM_PROVIDER
    wd_provider_cfg_value = initial.get(KEY_WD_LLM_PROVIDER_CONFIG_JSON) or initial.get(KEY_LLM_PROVIDER_CONFIG_JSON) or DEFAULT_LLM_PROVIDER_CONFIG_JSON
    wd_ollama_host_value = initial.get(KEY_WD_OLLAMA_HOST) or initial.get(KEY_OLLAMA_HOST) or DEFAULT_OLLAMA_HOST
    wd_ollama_model_value = initial.get(KEY_WD_OLLAMA_MODEL) or initial.get(KEY_OLLAMA_MODEL) or DEFAULT_OLLAMA_MODEL

    rl_provider_value = initial.get(KEY_RL_LLM_PROVIDER) or wd_provider_value
    rl_provider_cfg_value = initial.get(KEY_RL_LLM_PROVIDER_CONFIG_JSON) or wd_provider_cfg_value
    rl_ollama_host_value = initial.get(KEY_RL_OLLAMA_HOST) or wd_ollama_host_value
    rl_ollama_model_value = initial.get(KEY_RL_OLLAMA_MODEL) or wd_ollama_model_value

    chat_history_dir_value = initial.get(KEY_CHAT_HISTORY_DIR) or _default_chat_history_dir()
    mydata_dir_value = initial.get(KEY_MYDATA_DIR) or DEFAULT_MYDATA_DIR
    rag_embedding_model_value = initial.get(KEY_RAG_EMBEDDING_MODEL) or DEFAULT_RAG_EMBEDDING_MODEL
    rag_offline_value = bool(initial.get(KEY_RAG_OFFLINE, DEFAULT_RAG_OFFLINE))

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
        hint_text="e.g. llama3.2",
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
        hint_text="e.g. chat_history (relative to repo) or /abs/path/chat_history",
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

    def save_click(_e: ft.ControlEvent) -> None:
        new_project = (project_field.value or "").strip() or _default_project_name()
        new_template = (template_field.value or "").strip() or _default_workflow_save_path_template()
        wd_provider = (wd_llm_provider_dd.value or "").strip() or DEFAULT_LLM_PROVIDER
        wd_provider_cfg = (wd_llm_provider_config_field.value or "").strip()
        wd_host = (wd_ollama_host_field.value or "").strip() or DEFAULT_OLLAMA_HOST
        wd_model = (wd_ollama_model_field.value or "").strip() or DEFAULT_OLLAMA_MODEL

        rl_provider = (rl_llm_provider_dd.value or "").strip() or DEFAULT_LLM_PROVIDER
        rl_provider_cfg = (rl_llm_provider_config_field.value or "").strip()
        rl_host = (rl_ollama_host_field.value or "").strip() or DEFAULT_OLLAMA_HOST
        rl_model = (rl_ollama_model_field.value or "").strip() or DEFAULT_OLLAMA_MODEL

        new_chat_dir = (chat_history_dir_field.value or "").strip() or _default_chat_history_dir()
        new_mydata_dir = (mydata_dir_field.value or "").strip() or DEFAULT_MYDATA_DIR
        new_rag_model = (rag_embedding_model_dd.value or "").strip() or DEFAULT_RAG_EMBEDDING_MODEL
        new_rag_offline = bool(rag_offline_cb.value)
        try:
            save_settings(
                workflow_project_name=new_project,
                workflow_save_path_template=new_template,
                workflow_designer_llm_provider=wd_provider,
                workflow_designer_llm_provider_config_json=wd_provider_cfg,
                workflow_designer_ollama_host=wd_host,
                workflow_designer_ollama_model=wd_model,
                rl_coach_llm_provider=rl_provider,
                rl_coach_llm_provider_config_json=rl_provider_cfg,
                rl_coach_ollama_host=rl_host,
                rl_coach_ollama_model=rl_model,
                chat_history_dir=new_chat_dir,
                mydata_dir=new_mydata_dir,
                rag_embedding_model=new_rag_model,
                rag_offline=new_rag_offline,
            )
            project_field.value = new_project
            template_field.value = new_template
            wd_llm_provider_dd.value = wd_provider
            wd_llm_provider_config_field.value = wd_provider_cfg
            wd_ollama_host_field.value = wd_host
            wd_ollama_model_field.value = wd_model

            rl_llm_provider_dd.value = rl_provider
            rl_llm_provider_config_field.value = rl_provider_cfg
            rl_ollama_host_field.value = rl_host
            rl_ollama_model_field.value = rl_model

            chat_history_dir_field.value = new_chat_dir
            mydata_dir_field.value = new_mydata_dir
            rag_embedding_model_dd.value = new_rag_model
            rag_offline_cb.value = new_rag_offline
            project_field.update()
            template_field.update()
            wd_llm_provider_dd.update()
            wd_llm_provider_config_field.update()
            wd_ollama_host_field.update()
            wd_ollama_model_field.update()
            rl_llm_provider_dd.update()
            rl_llm_provider_config_field.update()
            rl_ollama_host_field.update()
            rl_ollama_model_field.update()
            chat_history_dir_field.update()
            mydata_dir_field.update()
            rag_embedding_model_dd.update()
            rag_offline_cb.update()
            if on_saved:
                on_saved()
            page.snack_bar = ft.SnackBar(content=ft.Text("Settings saved."), open=True)
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
