from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional

import flet as ft


@dataclass
class ChatComposerParts:
    input_tf: ft.TextField
    stop_btn: ft.IconButton
    upload_btn: ft.IconButton
    container: ft.Container


class ChatLayoutComponent:
    """
    Refactor of the previous builders.
    Public attributes kept for backward compatibility:
      - composer_parts: ChatComposerParts
      - build_history_row_with_model(...) and build_chat_inner_column(...) methods
    Added helpers:
      - show_stop(), hide_stop(), set_stop_visible(bool)
      - set_upload_enabled(bool)
    """

    # style constants (easy to change in one place)
    ICON_SIZE = 18
    PADDING_LEFT = 12
    PADDING_RIGHT = 12
    PADDING_TOP = 2
    PADDING_BOTTOM = 34
    BORDER_RADIUS = 6
    TEXT_SIZE = 12
    SPACING = 8
    BUTTONS_RIGHT = 6
    BUTTONS_BOTTOM = 6

    def __init__(
        self,
        *,
        min_lines: int = 1,
        max_lines: int = 6,
        on_stop_click: Optional[Callable[[object], None]] = None,
        on_upload_click: Optional[Callable[[object], None]] = None,
    ):
        self._on_stop_click = on_stop_click
        self._on_upload_click = on_upload_click

        self.composer_parts = self._build_chat_composer(
            min_lines=min_lines,
            max_lines=max_lines,
            on_stop_click=on_stop_click,
            on_upload_click=on_upload_click,
        )

    # --- Composer builder (returns ChatComposerParts) ---
    def _build_chat_composer(
        self,
        *,
        min_lines: int,
        max_lines: int,
        on_stop_click: Optional[Callable[[object], None]],
        on_upload_click: Optional[Callable[[object], None]],
    ) -> ChatComposerParts:
        composer_pad = ft.Padding.only(
            left=self.PADDING_LEFT,
            right=self.PADDING_RIGHT,
            top=self.PADDING_TOP,
            bottom=self.PADDING_BOTTOM,
        )

        input_tf = ft.TextField(
            hint_text="Message...",
            multiline=True,
            min_lines=min_lines,
            max_lines=max_lines,
            shift_enter=True,
            expand=True,
            text_style=ft.TextStyle(size=self.TEXT_SIZE),
            border=ft.InputBorder.OUTLINE,
            border_radius=self.BORDER_RADIUS,
            border_color=ft.Colors.GREY_700,
            focused_border_color=ft.Colors.BLUE_400,
            filled=True,
            fill_color=ft.Colors.with_opacity(0.06, ft.Colors.WHITE),
            content_padding=composer_pad,
        )

        stop_btn = ft.IconButton(
            icon=ft.Icons.STOP_CIRCLE,
            icon_size=self.ICON_SIZE,
            tooltip="Stop",
            padding=0,
            icon_color=ft.Colors.GREY_400,
            visible=False,
            on_click=on_stop_click,
        )

        upload_btn = ft.IconButton(
            icon=ft.Icons.UPLOAD_FILE,
            icon_size=self.ICON_SIZE,
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
                            controls=[upload_btn, stop_btn],
                            spacing=2,
                            alignment=ft.MainAxisAlignment.END,
                            vertical_alignment=ft.CrossAxisAlignment.END,
                        ),
                        right=self.BUTTONS_RIGHT,
                        bottom=self.BUTTONS_BOTTOM,
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

    # --- History row factory (keeps original signature) ---
    def build_history_row_with_model(
        self, history_row: ft.Control, model_label: ft.Text, *, visible: bool
    ) -> ft.Row:
        return ft.Row(
            controls=[
                history_row,
                ft.Container(expand=True),
                model_label,
            ],
            alignment=ft.MainAxisAlignment.SPACE_BETWEEN,
            visible=visible,
        )

    # --- Chat inner column builder (keeps original signature) ---
    def build_chat_inner_column(
        self,
        *,
        on_new_chat: Callable[[object], None],
        agent_dd: ft.Dropdown,
        chat_title_top_txt: ft.Text,
        refs_chips_row: ft.Control,
        top_input_container: ft.Control,
        history_row_top_with_model: ft.Control,
        messages_col: ft.Column,
        bottom_input_row: ft.Control,
        history_row_with_model: ft.Control,
    ) -> ft.Column:
        return ft.Column(
            controls=[
                ft.Row(
                    controls=[
                        ft.Container(expand=True),
                        ft.IconButton(
                            icon=ft.Icons.ADD,
                            icon_size=18,
                            tooltip="New chat",
                            on_click=on_new_chat,
                        ),
                        agent_dd,
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
            spacing=self.SPACING,
        )

    # --- Small helpers for common state updates (layout-focused) ---
    def show_stop(self, *, update: bool = True) -> None:
        self.composer_parts.stop_btn.visible = True
        if update:
            self.composer_parts.stop_btn.update()

    def hide_stop(self, *, update: bool = True) -> None:
        self.composer_parts.stop_btn.visible = False
        if update:
            self.composer_parts.stop_btn.update()

    def set_stop_visible(self, visible: bool, *, update: bool = True) -> None:
        self.composer_parts.stop_btn.visible = visible
        if update:
            self.composer_parts.stop_btn.update()

    def set_upload_enabled(self, enabled: bool, *, update: bool = True) -> None:
        self.composer_parts.upload_btn.disabled = not enabled
        if update:
            self.composer_parts.upload_btn.update()

    # Expose short aliases matching original builder names for drop-in replacement
    def build_chat_composer(
        self,
        *,
        min_lines: int,
        max_lines: int,
        on_stop_click: Callable[[object], None],
        on_upload_click: Callable[[object], None],
    ) -> ChatComposerParts:
        # preserve signature but return the already-built parts
        return self.composer_parts

    # Backwards-compatible properties for direct access
    @property
    def input_tf(self) -> ft.TextField:
        return self.composer_parts.input_tf

    @property
    def stop_btn(self) -> ft.IconButton:
        return self.composer_parts.stop_btn

    @property
    def upload_btn(self) -> ft.IconButton:
        return self.composer_parts.upload_btn

    @property
    def container(self) -> ft.Container:
        return self.composer_parts.container
