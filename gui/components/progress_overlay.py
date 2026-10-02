import flet as ft


def build_progress_overlay(default_message: str = ""):
    text = ft.Text(
        default_message,
        size=12,
        color=ft.Colors.GREY_400,
    )

    pulse = ft.Container(
        width=8,
        height=8,
        border_radius=4,
        bgcolor=ft.Colors.GREEN_ACCENT_400,
        scale=1,
        opacity=1,
        animate_scale=ft.Animation(
            duration=650,
            curve=ft.AnimationCurve.EASE_IN_OUT,
        ),
        animate_opacity=ft.Animation(
            duration=650,
            curve=ft.AnimationCurve.EASE_IN_OUT,
        ),
    )

    pulse_state = {"expanded": False}

    def animate_pulse():
        pulse_state["expanded"] = not pulse_state["expanded"]

        if pulse_state["expanded"]:
            pulse.scale = 1.8
            pulse.opacity = 0.35
        else:
            pulse.scale = 1
            pulse.opacity = 1

        pulse.update()

    pulse.on_animation_end = lambda e: animate_pulse()

    container = ft.Container(
        content=ft.Row(
            [
                pulse,
                text,
            ],
            alignment=ft.MainAxisAlignment.CENTER,
            spacing=8,
        ),
        left=0,
        right=200,
        top=20,
        visible=False,
    )

    overlay = ft.Stack(
        expand=True,
        controls=[container],
    )

    def show(message: str):
        text.value = message
        container.visible = True
        pulse_state["expanded"] = False
        pulse.scale = 1
        pulse.opacity = 1

        container.update()
        pulse.update()

        # Start the repeating pulse
        animate_pulse()

    def hide():
        container.visible = False
        container.update()

    return overlay, show, hide
