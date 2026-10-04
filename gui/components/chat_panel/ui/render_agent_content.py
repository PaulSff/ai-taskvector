from __future__ import annotations

from typing import Any

import flet as ft
from flet import Border, BorderSide

from gui.components.chat_panel.ui.render_helpers import (
    build_agent_plain_text_control,
    build_todo_preview_controls,
    compact_line_with_optional_success_icon,
    compact_meta_text_style,
    extract_edit_action,
    iter_action_dicts,
    parsed_is_no_action_only,
    parsed_is_query_display_only,
    parsed_is_todo_display_only,
    parsed_is_todo_mutators_only,
    query_display_lines,
    simulate_todo_actions,
    split_fenced_blocks,
    tex_arrows_to_unicode,
    todo_mutator_summary_lines,
    try_salvage_json_value,
)
from gui.utils.keyboard_commands import KeyboardCallback
from gui.utils.notifications import ToastCallback


async def render_agent_content(
    *,
    page: ft.Page,
    toast: ToastCallback,
    on_undo: KeyboardCallback | None,
    on_redo: KeyboardCallback | None,
    applied: bool,
    apply_failed: bool,
    content: str,
    bubble_width: int | None,
) -> ft.Control:
    segments = split_fenced_blocks(content)

    controls: list[ft.Control] = []

    text_style = ft.TextStyle(
        size=12,
        color=ft.Colors.GREY_200,
    )

    border_color = ft.Colors.with_opacity(
        0.18,
        ft.Colors.WHITE,
    )

    for kind, lang, chunk in segments:
        if not chunk:
            continue

        if kind == "hidden":
            hidden_parsed: Any = None

            candidate = try_salvage_json_value(chunk)
            if candidate is not None:
                hidden_parsed = candidate

            if parsed_is_query_display_only(hidden_parsed):
                q_lines = query_display_lines(hidden_parsed)
                controls.append(
                    ft.Column(
                        controls=[
                            ft.Text(
                                line,
                                **compact_meta_text_style(bubble_width=bubble_width),
                            )
                            for line in q_lines
                        ],
                        spacing=2,
                    )
                )
                continue

            if parsed_is_todo_display_only(hidden_parsed):
                todo_items = iter_action_dicts(hidden_parsed)

                if parsed_is_todo_mutators_only(hidden_parsed):
                    m_lines = todo_mutator_summary_lines(todo_items)
                    show_success_icon = bool(applied and apply_failed is False)

                    if m_lines:
                        if len(m_lines) == 1:
                            controls.append(
                                compact_line_with_optional_success_icon(
                                    m_lines[0],
                                    bubble_width=bubble_width,
                                    show_success_icon=show_success_icon,
                                )
                            )
                        else:
                            controls.append(
                                ft.Column(
                                    controls=[
                                        compact_line_with_optional_success_icon(
                                            line,
                                            bubble_width=bubble_width,
                                            show_success_icon=show_success_icon,
                                        )
                                        for line in m_lines
                                    ],
                                    spacing=2,
                                )
                            )
                    continue

                final_list, twarnings, removed_flag = simulate_todo_actions(todo_items)
                todo_controls = build_todo_preview_controls(
                    final_list,
                    twarnings,
                    list_explicitly_removed=removed_flag,
                    bubble_width=bubble_width,
                )

                if todo_controls:
                    controls.append(
                        ft.Column(
                            controls=todo_controls,
                            spacing=6,
                        )
                    )
                continue

            continue


        if kind == "text":
            ctrl = build_agent_plain_text_control(
                tex_arrows_to_unicode(chunk),
                text_style=text_style,
                bubble_width=bubble_width,
            )
            if ctrl is None:
                continue
            controls.append(ctrl)
            continue

        code_body_raw = chunk

        parsed: Any = None
        action_type: str | None = None
        edit_count = 0

        candidate = try_salvage_json_value(code_body_raw)
        if candidate is not None:
            parsed = candidate
            action_type = extract_edit_action(parsed)

        if isinstance(parsed, dict):
            if parsed.get("action") not in (None, "no_action"):
                edit_count = 1
        elif isinstance(parsed, list):
            edit_count = sum(
                1
                for e in parsed
                if isinstance(e, dict) and e.get("action") not in (None, "no_action")
            )

        failed = apply_failed and action_type not in (None, "no_action")

        if parsed_is_no_action_only(parsed):
            controls.append(
                ft.Text(
                    "No changes were made to the flow.",
                    **compact_meta_text_style(bubble_width=bubble_width),
                )
            )
            continue

        if parsed_is_query_display_only(parsed):
            q_lines = query_display_lines(parsed)
            controls.append(
                ft.Column(
                    controls=[
                        ft.Text(
                            line,
                            **compact_meta_text_style(bubble_width=bubble_width),
                        )
                        for line in q_lines
                    ],
                    spacing=2,
                )
            )
            continue

        if parsed_is_todo_display_only(parsed):
            todo_items = iter_action_dicts(parsed)

            if parsed_is_todo_mutators_only(parsed):
                m_lines = todo_mutator_summary_lines(todo_items)
                show_success_icon = bool(applied and not failed)

                if m_lines:
                    if len(m_lines) == 1:
                        controls.append(
                            compact_line_with_optional_success_icon(
                                m_lines[0],
                                bubble_width=bubble_width,
                                show_success_icon=show_success_icon,
                            )
                        )
                    else:
                        controls.append(
                            ft.Column(
                                controls=[
                                    compact_line_with_optional_success_icon(
                                        line,
                                        bubble_width=bubble_width,
                                        show_success_icon=show_success_icon,
                                    )
                                    for line in m_lines
                                ],
                                spacing=2,
                            )
                        )
                continue

            final_list, twarnings, removed_flag = simulate_todo_actions(todo_items)
            todo_controls = build_todo_preview_controls(
                final_list,
                twarnings,
                list_explicitly_removed=removed_flag,
                bubble_width=bubble_width,
            )

            if todo_controls:
                controls.append(
                    ft.Column(
                        controls=todo_controls,
                        spacing=6,
                    )
                )
            continue

        header_text = ""

        if edit_count > 0:
            header_text = f"{edit_count} edit{'s' if edit_count != 1 else ''}"

        if failed:
            header_text += " (failed)"

        def _copy_code(
            e: ft.Event[ft.IconButton],
            _text: str = code_body_raw,
        ) -> None:
            async def _run() -> None:
                try:
                    await ft.Clipboard().set(_text)
                    toast("Copied!")
                except PermissionError:
                    pass

            page.run_task(_run)

        def _do_undo(
            e: ft.Event[ft.IconButton],
        ) -> None:
            if on_undo:
                try:
                    on_undo()
                except (ValueError, RuntimeError):
                    pass

        def _do_redo(
            e: ft.Event[ft.IconButton],
        ) -> None:
            if on_redo:
                try:
                    on_redo()
                except (ValueError, RuntimeError):
                    pass

        code_lang = (lang or "json").strip().lower()

        LINE_HEIGHT = 18
        COLLAPSED_LINES = 6

        lines = code_body_raw.splitlines()
        total_lines = len(lines)

        collapsed_height = COLLAPSED_LINES * LINE_HEIGHT
        full_height = max(total_lines, 1) * LINE_HEIGHT

        expanded_ref: list[bool] = [False]

        fenced = (
            f"```{code_lang}\n{code_body_raw}\n```"
            if code_lang
            else f"```\n{code_body_raw}\n```"
        )

        code_display_control = ft.Markdown(
            value=fenced,
            selectable=True,
            extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
            code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
            code_style_sheet=ft.MarkdownStyleSheet(
                code_text_style=ft.TextStyle(font_family="Roboto Mono"),
            ),
        )

        code_container_ref: list[ft.Container | None] = [None]

        def set_code_height(_h: float, ref=code_container_ref) -> None:
            c = ref[0]
            if c is None:
                return
            c.height = _h
            c.update()
            page.update()

        code_container = ft.Container(
            content=code_display_control,
            height=collapsed_height,
            clip_behavior=ft.ClipBehavior.HARD_EDGE,
        )
        code_container_ref[0] = code_container

        toggle_btn_ref: list[ft.IconButton | None] = [None]

        def _toggle_code_block(
            e: ft.Event[ft.IconButton],
            *,
            toggle_btn_ref=toggle_btn_ref,
            expanded_ref=expanded_ref,
            set_code_height=set_code_height,
            full_height=full_height,
            collapsed_height=collapsed_height,
        ) -> None:
            btn = toggle_btn_ref[0]
            if btn is None:
                return

            expanded_ref[0] = not expanded_ref[0]

            if expanded_ref[0]:
                set_code_height(full_height)
                btn.icon = ft.Icons.EXPAND_LESS
                btn.tooltip = "Show less"
            else:
                set_code_height(collapsed_height)
                btn.icon = ft.Icons.EXPAND_MORE
                btn.tooltip = "Show more"

            btn.update()
            page.update()

        _controls_style = ft.ButtonStyle(
            padding=2,
            shape=ft.RoundedRectangleBorder(radius=4),
        )

        toggle_btn = ft.IconButton(
            icon=ft.Icons.EXPAND_MORE,
            icon_size=16,
            style=_controls_style,
            tooltip="Show more",
            on_click=_toggle_code_block,
            padding=2,
            width=16,
            height=16,
            visible=total_lines > COLLAPSED_LINES,
        )

        toggle_btn_ref[0] = toggle_btn

        header_controls: list[ft.Control] = [
            ft.Container(expand=True),
            ft.Text(
                ("Applied" if applied and edit_count > 0 else ""),
                size=10,
                color=ft.Colors.GREEN_400,
                visible=applied and edit_count > 0,
            ),
            ft.Text(
                header_text,
                size=10,
                color=(ft.Colors.ORANGE_300 if failed else ft.Colors.GREY_400),
                visible=bool(header_text),
            ),
            ft.IconButton(
                icon=ft.Icons.UNDO,
                icon_size=14,
                width=18,
                height=18,
                style=_controls_style,
                tooltip="Undo",
                on_click=_do_undo,
                visible=edit_count > 0,
                disabled=on_undo is None,
            ),
            ft.IconButton(
                icon=ft.Icons.REDO,
                icon_size=14,
                width=18,
                height=18,
                style=_controls_style,
                tooltip="Redo",
                on_click=_do_redo,
                visible=edit_count > 0,
                disabled=on_redo is None,
            ),
            ft.IconButton(
                icon=ft.Icons.CONTENT_COPY,
                icon_size=14,
                width=18,
                height=18,
                style=_controls_style,
                tooltip="Copy",
                on_click=_copy_code,
            ),
        ]

        body_controls: list[ft.Control] = [
            ft.Row(
                controls=header_controls,
                spacing=10,
            ),
            code_container,
            ft.Row(
                controls=[
                    ft.Container(expand=True),
                    toggle_btn,
                ],
                alignment=ft.MainAxisAlignment.END,
                visible=(total_lines > COLLAPSED_LINES),
            ),
        ]

        controls.append(
            ft.Container(
                content=ft.Column(
                    controls=body_controls,
                    spacing=4,
                ),
                padding=ft.Padding.only(
                    left=2,
                    right=2,
                    top=8,
                    bottom=8,
                ),
                border=Border(
                    top=BorderSide(1, border_color),
                    right=BorderSide(1, border_color),
                    bottom=BorderSide(1, border_color),
                    left=BorderSide(1, border_color),
                ),
                border_radius=8,
                bgcolor=ft.Colors.with_opacity(
                    0.02,
                    ft.Colors.WHITE,
                ),
            )
        )

    if not controls:
        fallback = build_agent_plain_text_control(
            tex_arrows_to_unicode(content),
            text_style=text_style,
            bubble_width=bubble_width,
        )
        if fallback is None:
            return ft.Text(
                tex_arrows_to_unicode(content),
                size=12,
                color=ft.Colors.GREY_200,
            )
        return fallback

    return ft.Column(
        controls=controls,
        spacing=6,
    )
