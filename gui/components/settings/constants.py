"""JSON key names and default values for ``config/app_settings.json``."""
from __future__ import annotations

SETTINGS_FILENAME = "app_settings.json"

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

KEY_LLM_PROVIDER = "llm_provider"  # legacy/global
DEFAULT_LLM_PROVIDER = "ollama"
KEY_LLM_PROVIDER_CONFIG_JSON = "llm_provider_config_json"  # legacy/global
DEFAULT_LLM_PROVIDER_CONFIG_JSON = ""
# Optional: for Ollama Cloud (https://ollama.com); also use env OLLAMA_API_KEY
KEY_OLLAMA_API_KEY = "ollama_api_key"
# Start Ollama server with app (so you don't run "ollama serve" separately)
KEY_START_OLLAMA_WITH_APP = "start_ollama_with_app"
KEY_OLLAMA_EXECUTABLE_PATH = "ollama_executable_path"

# Legacy JSON key names (no longer stored in app_settings.json); values live under ``llm:`` in role.yaml.
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
KEY_RAG_INDEX_DATA_DIR = "rag_index_data_dir"  # legacy; values in rag/ragconf.yaml
KEY_MYDATA_DIR = "mydata_dir"  # where user content to index lives (workflows, nodes, docs)
DEFAULT_RAG_INDEX_DATA_DIR = "rag/.rag_index_data"
DEFAULT_MYDATA_DIR = "mydata"

# RAG index dir / embedding / offline: ``rag/ragconf.yaml`` (see rag.ragconf_loader).
KEY_RAG_EMBEDDING_MODEL = "rag_embedding_model"
DEFAULT_RAG_EMBEDDING_MODEL = "sentence-transformers/all-MiniLM-L6-v2"
KEY_RAG_OFFLINE = "rag_offline"
DEFAULT_RAG_OFFLINE = False
# Legacy app_settings keys (no longer written to app_settings.json): values live in
# assistants/roles/*/role.yaml (rag.top_k) and assistants/tools/{rag_search,read_file}/tool.yaml (rag.*).
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
# Workflow Designer: allow list_unit / list_environment prompt lines (repo scaffolding). Shown only when native runtime and coding_is_allowed are also true.
KEY_CONTRIBUTION_IS_ALLOWED = "contribution_is_allowed"
DEFAULT_CONTRIBUTION_IS_ALLOWED = False
# Analyst chat: run RAG-based auto-delegation before the main assistant workflow when enabled.
KEY_AUTO_DELEGATION_IS_ALLOWED = "auto_delegation_is_allowed"
DEFAULT_AUTO_DELEGATION_IS_ALLOWED = False
# Legacy app_settings key; cap lives in ``assistants/roles/workflow_designer/role.yaml`` ``follow_up_max_rounds``.
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

# Assistant / chat workflow and prompt paths (relative to repo root; from app_settings.json where persisted).
# RAG context workflow path: ``assistants/tools/rag_search/tool.yaml`` ``workflow`` (see ``get_rag_context_workflow_path``).
# RAG update / doc-to-text workflow paths: ``rag/ragconf.yaml`` (see ``get_rag_update_workflow_path`` / ``get_doc_to_text_workflow_path``).
KEY_RAG_UPDATE_WORKFLOW_PATH = "rag_update_workflow_path"  # legacy app_settings key; migrated out to ragconf
KEY_CREATE_FILENAME_WORKFLOW_PATH = "create_filename_workflow_path"
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
