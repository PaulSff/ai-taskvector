import flet as ft
from pathlib import Path
import requests


def load_text(local_path: str | None = None, url: str | None = None) -> str:
    if local_path:
        return Path(local_path).read_text(encoding="utf-8")

    if url:
        resp = requests.get(url, timeout=20)
        resp.raise_for_status()
        return resp.text

    raise ValueError("Provide either local_path or url.")


def open_markdown_dialog(
    page: ft.Page,
    *,
    markdown: str | None = None,
    title: str = "Preview",
    width: int = 720,
    height: int = 520,
    local_path: str | None = None,
    url: str | None = None,
) -> None:
    if markdown is None:
        markdown = load_text(local_path=local_path, url=url)

    dialog = ft.AlertDialog(
        modal=True,
        title=ft.Text(title),
        content=ft.Container(
            width=width,
            height=height,
            content=ft.ListView(
                expand=True,
                spacing=0,
                padding=0,
                controls=[
                    ft.Markdown(
                        value=markdown,
                        selectable=True,
                        extension_set=ft.MarkdownExtensionSet.GITHUB_WEB,
                        code_theme=ft.MarkdownCodeTheme.ATOM_ONE_DARK,
                        on_tap_link=lambda e: page.launch_url(e.control.data),
                    )
                ],
            ),
        ),
        actions=[
            ft.TextButton("Close", on_click=lambda e: page.pop_dialog())
        ],
        actions_alignment=ft.MainAxisAlignment.END,
    )

    page.show_dialog(dialog)
    page.update()
