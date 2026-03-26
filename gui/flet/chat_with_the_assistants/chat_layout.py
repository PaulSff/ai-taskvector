from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import flet as ft


@dataclass
class ChatComposerParts:
    input_tf: ft.TextField
    stop_btn: ft.IconButton
    upload_btn: ft.IconButton
    container: ft.Container


def build_chat_composer(
    *,
    min_lines: int,
    max_lines: int,
    on_stop_click: Callable[[ft.ControlEvent], None],
    on_upload_click: Callable[[ft.ControlEvent], None],
) -> ChatComposerParts:
    composer_pad = ft.Padding.only(left=12, right=72, top=10, bottom=34)
    input_tf = ft.TextField(
        hint_text="Message...",
        multiline=True,
        min_lines=min_lines,
        max_lines=max_lines,
        shift_enter=True,
        expand=True,
        text_style=ft.TextStyle(size=12),
        border=ft.InputBorder.OUTLINE,
        border_radius=10,
        border_color=ft.Colors.GREY_700,
        focused_border_color=ft.Colors.BLUE_400,
        filled=True,
        fill_color=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
        content_padding=composer_pad,
    )
    stop_btn = ft.IconButton(
        icon=ft.Icons.STOP_CIRCLE,
        icon_size=16,
        tooltip="Stop",
        padding=0,
        icon_color=ft.Colors.GREY_400,
        visible=False,
        on_click=on_stop_click,
    )
    upload_btn = ft.IconButton(
        icon=ft.Icons.UPLOAD_FILE,
        icon_size=16,
        tooltip="Add files",
        padding=0,
        icon_color=ft.Colors.GREY_400,
        on_click=on_upload_click,
    )
    container = ft.Container(
        expand=True,
        content=ft.Stack(
            expand=True,
            controls=[
                input_tf,
                ft.Container(
                    content=ft.Row(
                        [upload_btn, stop_btn],
                        spacing=2,
                        alignment=ft.MainAxisAlignment.END,
                        vertical_alignment=ft.CrossAxisAlignment.END,
                    ),
                    right=6,
                    bottom=6,
                ),
            ],
        ),
    )
    return ChatComposerParts(
        input_tf=input_tf,
        stop_btn=stop_btn,
        upload_btn=upload_btn,
        container=container,
    )


def build_history_row_with_model(history_row: ft.Control, model_label: ft.Text, *, visible: bool) -> ft.Row:
    return ft.Row(
        [
            history_row,
            ft.Container(expand=True),
            model_label,
        ],
        alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
        visible=visible,
    )


def build_chat_inner_column(
    *,
    on_new_chat: Callable[[ft.ControlEvent], None],
    assistant_dd: ft.Dropdown,
    chat_title_top_txt: ft.Text,
    refs_chips_row: ft.Control,
    top_input_container: ft.Control,
    history_row_top_with_model: ft.Control,
    messages_col: ft.Column,
    bottom_input_row: ft.Control,
    history_row_with_model: ft.Control,
) -> ft.Column:
    return ft.Column(
        [
            ft.Row(
                [
                    ft.Container(expand=True),
                    ft.IconButton(
                        icon=ft.Icons.ADD,
                        icon_size=18,
                        tooltip="New chat",
                        on_click=on_new_chat,
                    ),
                    assistant_dd,
                ],
                alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            ),
            chat_title_top_txt,
            refs_chips_row,
            top_input_container,
            history_row_top_with_model,
            ft.Container(content=messages_col, expand=True),
            bottom_input_row,
            history_row_with_model,
        ],
        expand=True,
        spacing=8,
    )
