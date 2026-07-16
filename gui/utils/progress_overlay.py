import flet as ft

def build_progress_overlay(default_message: str = ""):
    text = ft.Text(default_message, size=12, color=ft.Colors.GREY_400)

    container = ft.Container(
        content=ft.Row(
            [
                ft.ProgressRing(width=24, height=24, stroke_width=2),
                text,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=12,
        ),
        left=0,
        right=0,
        top=20,
        visible=False,
    )

    overlay = ft.Stack(expand=True, controls=[container])

    def show(message: str):
        text.value = message
        container.visible = True

    def hide():
        container.visible = False

    return overlay, show, hide
