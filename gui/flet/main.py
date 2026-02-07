"""
Constructor GUI: Flet + Canvas graph (desktop).
Run from repo root: python -m gui.flet.main
Or: flet run gui/flet/main.py
"""
import sys
from pathlib import Path

import flet as ft

REPO_ROOT = Path(__file__).resolve().parent.parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from normalizer import load_process_graph_from_file

from gui.flet.graph_canvas import build_graph_canvas


def main(page: ft.Page) -> None:
    page.title = "RL Agent gym (Flet)"
    page.theme_mode = ft.ThemeMode.DARK
    page.padding = 0

    # Load example process graph for Process tab
    example_path = REPO_ROOT / "config" / "examples" / "temperature_process.yaml"
    graph = None
    if example_path.exists():
        try:
            graph = load_process_graph_from_file(str(example_path), format="yaml")
        except Exception as e:
            print(f"Could not load example graph: {e}")

    # Process tab: pure Flet Canvas + Node controls
    if graph is not None:
        process_content = ft.Container(content=build_graph_canvas(page, graph), expand=True)
    else:
        process_content = ft.Container(
            content=ft.Column(
                [
                    ft.Text("Process graph", size=20, weight=ft.FontWeight.BOLD),
                    ft.Text("No process graph loaded. Add config/examples/temperature_process.yaml or load from file."),
                ],
                alignment=ft.MainAxisAlignment.CENTER,
                horizontal_alignment=ft.CrossAxisAlignment.CENTER,
            ),
            expand=True,
            alignment=ft.alignment.center,
        )

    # Placeholder tabs
    training_content = ft.Container(
        content=ft.Column(
            [
                ft.Text("Training config", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Load / edit training YAML and hyperparameters (placeholder)."),
            ],
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=24,
        expand=True,
    )
    run_content = ft.Container(
        content=ft.Column(
            [
                ft.Text("Run / Test", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Run training or test policy (placeholder)."),
            ],
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=24,
        expand=True,
    )
    assistant_content = ft.Container(
        content=ft.Column(
            [
                ft.Text("Assistant", size=20, weight=ft.FontWeight.BOLD),
                ft.Text("Chat with Workflow Designer / RL Coach (placeholder)."),
            ],
            alignment=ft.MainAxisAlignment.START,
        ),
        padding=24,
        expand=True,
    )

    contents = [process_content, training_content, run_content, assistant_content]
    content_col = ft.Column(controls=[contents[0]], expand=True)

    def on_rail_change(e: ft.ControlEvent) -> None:
        idx = e.control.selected_index or 0
        nav_rail.selected_index = idx
        content_col.controls = [contents[idx]]
        page.update()

    nav_rail = ft.NavigationRail(
        selected_index=0,
        label_type=ft.NavigationRailLabelType.ALL,
        min_width=100,
        destinations=[
            ft.NavigationRailDestination(icon=ft.Icons.ACCOUNT_TREE, label="Process"),
            ft.NavigationRailDestination(icon=ft.Icons.TUNE, label="Training"),
            ft.NavigationRailDestination(icon=ft.Icons.PLAY_ARROW, label="Run/Test"),
            ft.NavigationRailDestination(icon=ft.Icons.CHAT, label="Assistant"),
        ],
        on_change=on_rail_change,
    )

    page.add(
        ft.Row(
            [
                nav_rail,
                ft.VerticalDivider(width=1),
                content_col,
            ],
            expand=True,
        )
    )


if __name__ == "__main__":
    ft.app(target=main)
