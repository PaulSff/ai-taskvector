from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Literal

# ─────────────────────────────────────────────────────────────────────────────
# Pre-apply follow-up rounds
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class ParserFollowUpContext:
    """Bindings for run_parser_output_follow_up_chain."""

    page: object | None
    graph_ref: list[object]
    state: object
    token: str
    turn_id: str
    agent_label: str
    follow_up_contexts: list[str]
    max_rounds: int
    wf_language_hint: list[str]
    is_current_run: Callable[[object], bool]
    toast: Callable[[str], Awaitable[None]]
    set_inline_status: Callable[[str | None], None]
    append_message: Callable[..., None]
    prepare_stream_row: Callable[[], None]
    normalize_user_message_for_workflow: Callable[[str], str]
    last_apply_result_ref: list[object]
    get_recent_changes: Callable[[], str | None] | None
    overrides: dict[str, object]
    run_workflow_streaming: Callable[..., Awaitable[object]]
    get_runtime_for_prompts: Callable[
        [object],
        Awaitable[Literal["native", "external"]],
    ]
    format_previous_turn: Callable[
        [list[dict[str, object]]],
        Awaitable[str],
    ]
    on_show_run_console: Callable[..., None] | None = None

    # None means all Workflow Designer follow-up tools.
    # Otherwise, this is an allowlist of tool IDs from the catalog or role.yaml.
    follow_up_tool_ids: tuple[str, ...] | None = None

    # Workflow response dictionary for the current follow-up round.
    follow_up_source_response: dict[str, object] | None = None

    # agents.roles ID, such as "workflow_designer".
    # Used for RAG follow-ups, not only for the UI label.
    agent_role_id: str | None = None

    # When set, run_agent_workflow uses this JSON instead of
    # the Workflow Designer default.
    agent_workflow_path: Path | None = None

    # Analyst chat mode: slimmer injects and hidden graph structure
    # in summary overrides.
    analyst_mode: bool = False

    # When set, only these (tool_id, parser_key) pairs run in follow-up order.
    # Otherwise, the Workflow Designer catalog order is used.
    ordered_follow_up_tools: tuple[tuple[str, str], ...] | None = None

    # Optional development callback containing the response dictionary,
    # including llm_system_prompt and llm_user_message.
    record_llm_prompt_view: Callable[[dict[str, object]], None] | None = None

    # RL Coach and similar agents can merge training injects after
    # build_agent_workflow_initial_inputs.
    extend_agent_initial_inputs_async: (
        Callable[
            [dict[str, dict[str, object]]],
            Awaitable[dict[str, dict[str, object]]],
        ]
        | None
    ) = None


@dataclass
class WDFollowUpAcc:
    """Mutable accumulators for one parser follow-up round."""

    context_chunks: list[str] = field(default_factory=list)
    any_empty_tool: bool = False
    read_code_ids_for_msg: list[str] = field(default_factory=list)
    implementation_links_for_types: list[str] = field(default_factory=list)
    report_follow_up: bool = False
    formulas_calc_follow_up: bool = False
    calendar_follow_up: bool = False
    clone_role_follow_up: bool = False
    list_dir_follow_up: bool = False
    read_file_follow_up: bool = False


# ─────────────────────────────────────────────────────────────────────────────
# Post-apply follow-up rounds
# ─────────────────────────────────────────────────────────────────────────────


@dataclass
class PostApplyFollowUpContext:
    graph_ref: list[object]
    state: object
    token: object
    turn_id: str
    agent_role_id: str
    agent_label: str
    max_rounds: int
    wf_language_hint: list[str]
    is_current_run: Callable[[object], bool]
    toast: Callable[[str], Awaitable[None]]
    set_inline_status: Callable[[str | None], None]
    append_message: Callable[..., None]
    prepare_stream_row: Callable[[], None]
    normalize_user_message_for_workflow: Callable[[str], str]
    last_apply_result_ref: list[object]
    get_recent_changes: Callable[[], str | None] | None
    overrides: dict[str, object]
    run_workflow_streaming: Callable[..., Awaitable[object]]
    get_runtime_for_prompts: Callable[
        [object],
        Awaitable[Literal["native", "external"]],
    ]
    format_previous_turn: Callable[
        [list[dict[str, object]]],
        Awaitable[str],
    ]
    replace_agent_message_row: Callable[[dict[str, object]], None]
    stream_buffer_ref: list[str]
    apply_fn: Callable[[object], None]
    agent_workflow_path: Path | None = None
    analyst_mode: bool = False
    record_llm_prompt_view: Callable[[dict[str, object]], None] | None = field(
        default=None,
        kw_only=True,
    )


@dataclass
class PostApplyFlags:
    had_import_workflow: bool
    had_todo: bool
    had_add_comment: bool
