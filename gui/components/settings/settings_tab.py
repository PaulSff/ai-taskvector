"""Flet UI for the Settings tab."""
from __future__ import annotations

import asyncio
from typing import Any, Callable

import flet as ft

from gui.utils.notifications import show_toast
from gui.utils.role_settings_discovery import discover_role_llm_ui_entries

from .constants import (
    DEFAULT_LLM_PROVIDER,
    DEFAULT_OLLAMA_HOST,
    DEFAULT_OLLAMA_MODEL,
    DEFAULT_RAG_EMBEDDING_MODEL,
    DEFAULT_CODING_IS_ALLOWED,
    DEFAULT_CONTRIBUTION_IS_ALLOWED,
    DEFAULT_DEBUG_LOG_PATH,
    DEFAULT_TRAINING_CONFIG_PATH,
    DEFAULT_WORKFLOW_DESIGNER_PROMPT_PATH,
    DEFAULT_RL_COACH_PROMPT_PATH,
    DEFAULT_CREATE_FILENAME_PROMPT_PATH,
    DEFAULT_MYDATA_DIR,
    DEFAULT_WORKFLOW_UNDO_MAX_DEPTH,
    DEFAULT_CHAT_STREAM_UI_INTERVAL_MS,
    KEY_BEST_MODEL_PATH,
    KEY_CHAT_HISTORY_DIR,
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
    KEY_RL_COACH_PROMPT_PATH,
    KEY_START_OLLAMA_WITH_APP,
    KEY_TRAINING_CONFIG_PATH,
    KEY_WORKFLOW_DESIGNER_PROMPT_PATH,
    KEY_WORKFLOW_PROJECT_NAME,
    KEY_WORKFLOW_SAVE_PATH_TEMPLATE,
    KEY_WORKFLOW_UNDO_MAX_DEPTH,
    KEY_CHAT_STREAM_UI_INTERVAL_MS,
    MIN_WORKFLOW_UNDO_MAX_DEPTH,
    MAX_WORKFLOW_UNDO_MAX_DEPTH,
    MIN_CHAT_STREAM_UI_INTERVAL_MS,
    MAX_CHAT_STREAM_UI_INTERVAL_MS,
    SETTINGS_FILENAME,
)
from .getters import (
    _default_chat_history_dir,
    _default_project_name,
    _default_workflow_save_path_template,
    get_chat_stream_ui_interval_ms,
    get_workflow_undo_max_depth,
    list_llm_providers,
)
from .paths import REPO_ROOT
from .persistence import load_settings, save_settings
from .role_yaml import _role_llm_str


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
    legacy_ollama_host = initial.get(KEY_OLLAMA_HOST)
    legacy_ollama_model = initial.get(KEY_OLLAMA_MODEL)

    def _initial_llm_row_for_role(role_id: str) -> tuple[str, str, str, str]:
        prov = _role_llm_str(role_id, "provider", default=DEFAULT_LLM_PROVIDER)
        cfg = _role_llm_str(role_id, "provider_config_json", default="")
        if role_id == "workflow_designer":
            host = (
                _role_llm_str(role_id, "ollama_host", default=DEFAULT_OLLAMA_HOST)
                or (str(legacy_ollama_host).strip() if legacy_ollama_host is not None else "")
                or DEFAULT_OLLAMA_HOST
            )
            model = (
                _role_llm_str(role_id, "ollama_model", default=DEFAULT_OLLAMA_MODEL)
                or (str(legacy_ollama_model).strip() if legacy_ollama_model is not None else "")
                or DEFAULT_OLLAMA_MODEL
            )
        else:
            fb_h = (
                _role_llm_str("workflow_designer", "ollama_host", default=DEFAULT_OLLAMA_HOST)
                or (str(legacy_ollama_host).strip() if legacy_ollama_host is not None else "")
                or DEFAULT_OLLAMA_HOST
            )
            fb_m = (
                _role_llm_str("workflow_designer", "ollama_model", default=DEFAULT_OLLAMA_MODEL)
                or (str(legacy_ollama_model).strip() if legacy_ollama_model is not None else "")
                or DEFAULT_OLLAMA_MODEL
            )
            host = _role_llm_str(role_id, "ollama_host", default=fb_h) or fb_h
            model = _role_llm_str(role_id, "ollama_model", default=fb_m) or fb_m
        return prov, cfg, host, model

    llm_role_widgets: dict[str, dict[str, Any]] = {}
    llm_column_children: list[ft.Control] = []
    for entry in discover_role_llm_ui_entries():
        pv, cv, hv, mv = _initial_llm_row_for_role(entry.role_id)
        prov_dd = ft.Dropdown(
            label=f"{entry.role_name}: LLM provider",
            value=str(pv),
            width=220,
            height=36,
            text_style=ft.TextStyle(size=12),
            options=[ft.dropdown.Option(p) for p in list_llm_providers()],
        )
        prov_cfg_f = ft.TextField(
            label=f"{entry.role_name}: provider config (JSON, optional)",
            value=cv,
            hint_text='e.g. {"host":"http://127.0.0.1:11434","model":"llama3.2"}',
            width=400,
            text_style=ft.TextStyle(font_family="monospace", size=12),
            multiline=True,
            min_lines=2,
            max_lines=6,
        )
        host_f = ft.TextField(
            label=f"{entry.role_name}: Ollama server (host:port)",
            value=hv,
            hint_text="e.g. http://127.0.0.1:11434",
            width=400,
            text_style=ft.TextStyle(font_family="monospace", size=12),
        )
        model_f = ft.TextField(
            label=f"{entry.role_name}: Ollama model",
            value=mv,
            hint_text="e.g. llama3.2 or qwen3-coder:480b-cloud for Cloud",
            width=400,
            text_style=ft.TextStyle(font_family="monospace", size=12),
        )
        llm_role_widgets[entry.role_id] = {
            "provider": prov_dd,
            "config": prov_cfg_f,
            "host": host_f,
            "model": model_f,
        }
        llm_column_children.extend(
            [
                prov_dd,
                ft.Container(height=8),
                prov_cfg_f,
                ft.Container(height=8),
                host_f,
                ft.Container(height=8),
                model_f,
                ft.Container(height=16),
            ]
        )

    ollama_api_key_value = (initial.get(KEY_OLLAMA_API_KEY) or "").strip()
    start_ollama_with_app_value = bool(initial.get(KEY_START_OLLAMA_WITH_APP, False))
    ollama_executable_path_value = (initial.get(KEY_OLLAMA_EXECUTABLE_PATH) or "").strip()
    chat_history_dir_value = initial.get(KEY_CHAT_HISTORY_DIR) or _default_chat_history_dir()
    mydata_dir_value = initial.get(KEY_MYDATA_DIR) or DEFAULT_MYDATA_DIR
    from rag.ragconf_loader import rag_embedding_model_raw, rag_offline_raw

    rag_embedding_model_value = rag_embedding_model_raw()
    rag_offline_value = bool(rag_offline_raw())
    coding_is_allowed_value = bool(initial.get(KEY_CODING_IS_ALLOWED, DEFAULT_CODING_IS_ALLOWED))
    contribution_is_allowed_value = bool(initial.get(KEY_CONTRIBUTION_IS_ALLOWED, DEFAULT_CONTRIBUTION_IS_ALLOWED))
    workflow_undo_max_depth_value = get_workflow_undo_max_depth()
    chat_stream_ui_interval_ms_value = get_chat_stream_ui_interval_ms()
    debug_log_path_value = initial.get(KEY_DEBUG_LOG_PATH) or DEFAULT_DEBUG_LOG_PATH
    create_filename_workflow_path_value = (initial.get(KEY_CREATE_FILENAME_WORKFLOW_PATH) or "").strip()
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
        label="Create filename workflow path (optional override)",
        value=create_filename_workflow_path_value,
        hint_text="Leave empty to use assistants/roles/chat_name_creator/role.yaml chat.workflow",
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
    contribution_is_allowed_cb = ft.Checkbox(
        label="Workflow Designer: allow repo contribution prompts (list_unit / list_environment). Only injected when graph runtime is native and custom code is allowed above.",
        value=contribution_is_allowed_value,
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
        role_llm_updates: dict[str, dict[str, Any]] = {}
        for rid, w in llm_role_widgets.items():
            role_llm_updates[rid] = {
                "provider": (w["provider"].value or "").strip() or DEFAULT_LLM_PROVIDER,
                "provider_config_json": (w["config"].value or "").strip(),
                "ollama_host": (w["host"].value or "").strip() or DEFAULT_OLLAMA_HOST,
                "ollama_model": (w["model"].value or "").strip() or DEFAULT_OLLAMA_MODEL,
            }
        ollama_api_key = (ollama_api_key_field.value or "").strip()
        start_ollama = bool(start_ollama_with_app_cb.value)
        ollama_path = (ollama_executable_path_field.value or "").strip()

        new_chat_dir = (chat_history_dir_field.value or "").strip() or _default_chat_history_dir()
        new_mydata_dir = (mydata_dir_field.value or "").strip() or DEFAULT_MYDATA_DIR
        new_rag_model = (rag_embedding_model_dd.value or "").strip() or DEFAULT_RAG_EMBEDDING_MODEL
        new_rag_offline = bool(rag_offline_cb.value)
        new_coding_is_allowed = bool(coding_is_allowed_cb.value)
        new_contribution_is_allowed = bool(contribution_is_allowed_cb.value)
        try:
            new_workflow_undo_max_depth = int((workflow_undo_max_depth_field.value or "").strip())
        except (TypeError, ValueError):
            new_workflow_undo_max_depth = DEFAULT_WORKFLOW_UNDO_MAX_DEPTH
        try:
            new_chat_stream_ui_interval_ms = int((chat_stream_ui_interval_ms_field.value or "").strip())
        except (TypeError, ValueError):
            new_chat_stream_ui_interval_ms = DEFAULT_CHAT_STREAM_UI_INTERVAL_MS
        new_debug_log_path = (debug_log_path_field.value or "").strip() or DEFAULT_DEBUG_LOG_PATH
        new_create_filename_workflow_path = (create_filename_workflow_path_field.value or "").strip()
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
                role_llm_updates=role_llm_updates,
                ollama_api_key=ollama_api_key,
                start_ollama_with_app=start_ollama,
                ollama_executable_path=ollama_path,
                chat_history_dir=new_chat_dir,
                mydata_dir=new_mydata_dir,
                rag_embedding_model=new_rag_model,
                rag_offline=new_rag_offline,
                coding_is_allowed=new_coding_is_allowed,
                contribution_is_allowed=new_contribution_is_allowed,
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
            for rid, patch in role_llm_updates.items():
                w = llm_role_widgets.get(rid)
                if not w:
                    continue
                w["provider"].value = patch["provider"]
                w["config"].value = patch["provider_config_json"]
                w["host"].value = patch["ollama_host"]
                w["model"].value = patch["ollama_model"]
            ollama_api_key_field.value = ollama_api_key
            start_ollama_with_app_cb.value = start_ollama
            ollama_executable_path_field.value = ollama_path

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
            for w in llm_role_widgets.values():
                w["provider"].update()
                w["config"].update()
                w["host"].update()
                w["model"].update()
            ollama_api_key_field.update()
            start_ollama_with_app_cb.update()
            ollama_executable_path_field.update()
            chat_history_dir_field.update()
            mydata_dir_field.update()
            rag_embedding_model_dd.update()
            rag_offline_cb.update()
            coding_is_allowed_cb.update()
            contribution_is_allowed_cb.update()
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
                ft.Text(
                    "Per-role LLM settings are loaded from assistants/roles/<role_id>/role.yaml (llm:). "
                    "Roles are discovered automatically; use settings.show_llm_ui: false to hide a role.",
                    size=12,
                    color=ft.Colors.GREY_500,
                ),
                ft.Container(height=8),
                *llm_column_children,
                ft.Text("Ollama (shared)", size=12, weight=ft.FontWeight.W_600, color=ft.Colors.GREY_400),
                ft.Container(height=8),
                ollama_api_key_field,
                ft.Container(height=8),
                start_ollama_with_app_cb,
                ft.Container(height=4),
                ollama_executable_path_field,
                ft.Container(height=16),
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
                contribution_is_allowed_cb,
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
