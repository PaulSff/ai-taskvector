"""
Configurable styling for workflow graph nodes and links (edges + arrows).
Keys: node type (unit.type, e.g. Source, Valve) and link type (e.g. default).
"""
from __future__ import annotations

from dataclasses import dataclass

import flet as ft


# Default node dimensions when not overridden per type
DEFAULT_NODE_WIDTH = 120
DEFAULT_NODE_HEIGHT = 50

# Port layout (input/output dots on node left/right)
PORT_ROW_HEIGHT = 16
PORT_DOT_RADIUS = 4


def _resolve_color(name: str) -> str:
    """Resolve a color name (e.g. 'grey_800', 'blue_400') to Flet color value."""
    key = name.upper().replace("-", "_").replace(" ", "_")
    return getattr(ft.Colors, key, name)


@dataclass(frozen=True)
class NodeStyle:
    """Style for a node (unit) type. Color names use Flet names, e.g. grey_800, blue_400."""

    bgcolor: str = "grey_800"
    border_color: str = "grey_600"
    text_color: str = "white"
    text_secondary_color: str = "grey_400"
    border_radius: int = 6
    bg_highlight: str = "grey_700"
    border_highlight: str = "blue_400"
    width: int | None = None
    height: int | None = None
    icon: str | None = None  # Material Icons name, e.g. "psychology" for brain

    def resolve(self) -> ResolvedNodeStyle:
        return ResolvedNodeStyle(
            bgcolor=_resolve_color(self.bgcolor),
            border_color=_resolve_color(self.border_color),
            text_color=_resolve_color(self.text_color),
            text_secondary_color=_resolve_color(self.text_secondary_color),
            border_radius=self.border_radius,
            bg_highlight=_resolve_color(self.bg_highlight),
            border_highlight=_resolve_color(self.border_highlight),
            width=self.width if self.width is not None else DEFAULT_NODE_WIDTH,
            height=self.height if self.height is not None else DEFAULT_NODE_HEIGHT,
            icon=self.icon,
        )


@dataclass(frozen=True)
class ResolvedNodeStyle:
    """Node style with resolved Flet color values."""

    bgcolor: str
    border_color: str
    text_color: str
    text_secondary_color: str
    border_radius: int
    bg_highlight: str
    border_highlight: str
    width: int
    height: int
    icon: str | None


@dataclass(frozen=True)
class LinkStyle:
    """Style for a link type (edge line + arrow). Color names as in NodeStyle."""

    line_color: str = "grey_500"
    arrow_color: str = "grey_500"
    stroke_width: int = 1
    arrow_length: int = 12
    arrow_half_width: int = 5
    line_highlight: str = "blue_400"
    arrow_highlight: str = "blue_400"

    def resolve(self) -> ResolvedLinkStyle:
        return ResolvedLinkStyle(
            edge_paint=ft.Paint(
                stroke_width=self.stroke_width,
                color=_resolve_color(self.line_color),
                style=ft.PaintingStyle.STROKE,
            ),
            arrow_paint=ft.Paint(style=ft.PaintingStyle.FILL, color=_resolve_color(self.arrow_color)),
            edge_paint_highlight=ft.Paint(
                stroke_width=self.stroke_width,
                color=_resolve_color(self.line_highlight),
                style=ft.PaintingStyle.STROKE,
            ),
            arrow_paint_highlight=ft.Paint(
                style=ft.PaintingStyle.FILL,
                color=_resolve_color(self.arrow_highlight),
            ),
            arrow_length=self.arrow_length,
            arrow_half_width=self.arrow_half_width,
        )


@dataclass(frozen=True)
class ResolvedLinkStyle:
    """Link style with resolved Flet paints and arrow dimensions."""

    edge_paint: ft.Paint
    arrow_paint: ft.Paint
    edge_paint_highlight: ft.Paint
    arrow_paint_highlight: ft.Paint
    arrow_length: int
    arrow_half_width: int


# Link type keys for RLAgent: incoming observations (to agent) = green, outgoing (to controls) = orange
LINK_TYPE_INCOMING_RL = "incoming_rl"
LINK_TYPE_OUTGOING_CONTROL = "outgoing_control"

# Default styles per node type and link type.
# Process units: Source, Valve, Tank, Sensor. Canonical training units: StepDriver, StepRewards, Join, Switch, Split, HttpIn, HttpResponse.
DEFAULT_NODE_STYLES: dict[str, NodeStyle] = {
    "default": NodeStyle(),
    # Process (simulator) units
    "Source": NodeStyle(bgcolor="grey_800", border_color="green_700"),
    "Valve": NodeStyle(bgcolor="grey_800", border_color="orange_700"),
    "Tank": NodeStyle(bgcolor="grey_800", border_color="blue_700"),
    "Sensor": NodeStyle(bgcolor="grey_800", border_color="teal_700"),
    # Agent (in-graph policy)
    "RLAgent": NodeStyle(
        bgcolor="grey_800",
        border_color="purple_700",
        width=180,
        height=75,
        icon="psychology",
    ),
    "LLMAgent": NodeStyle(
        bgcolor="grey_800",
        border_color="indigo_400",
        width=180,
        height=75,
        icon="smart_toy",
    ),
    # Canonical training-flow units
    "StepDriver": NodeStyle(
        bgcolor="grey_800",
        border_color="amber_700",
        border_highlight="amber_400",
        width=130,
        height=56,
        icon="play_arrow",
    ),
    "StepRewards": NodeStyle(
        bgcolor="grey_800",
        border_color="teal_600",
        border_highlight="teal_400",
        width=130,
        height=56,
        icon="emoji_events",
    ),
    "Join": NodeStyle(
        bgcolor="grey_800",
        border_color="indigo_600",
        border_highlight="indigo_400",
        width=110,
        height=50,
        icon="merge_type",
    ),
    "Switch": NodeStyle(
        bgcolor="grey_800",
        border_color="orange_600",
        border_highlight="orange_400",
        width=110,
        height=50,
        icon="account_tree",
    ),
    "Split": NodeStyle(
        bgcolor="grey_800",
        border_color="purple_600",
        border_highlight="purple_400",
        width=110,
        height=50,
        icon="call_split",
    ),
    "HttpIn": NodeStyle(
        bgcolor="grey_800",
        border_color="cyan_600",
        border_highlight="cyan_400",
        width=100,
        height=46,
        icon="input",
    ),
    "HttpResponse": NodeStyle(
        bgcolor="grey_800",
        border_color="grey_500",
        border_highlight="grey_400",
        width=110,
        height=46,
        icon="output",
    ),
}

DEFAULT_LINK_STYLES: dict[str, LinkStyle] = {
    "default": LinkStyle(),
    LINK_TYPE_INCOMING_RL: LinkStyle(
        line_color="green_600",
        arrow_color="green_600",
        line_highlight="green_400",
        arrow_highlight="green_400",
    ),
    LINK_TYPE_OUTGOING_CONTROL: LinkStyle(
        line_color="orange_600",
        arrow_color="orange_600",
        line_highlight="orange_400",
        arrow_highlight="orange_400",
    ),
}

# Full config: node type -> NodeStyle, link type -> LinkStyle
GraphStyleConfig = tuple[dict[str, NodeStyle], dict[str, LinkStyle]]


def get_default_style_config() -> GraphStyleConfig:
    return (dict(DEFAULT_NODE_STYLES), dict(DEFAULT_LINK_STYLES))


def get_node_style(
    node_styles: dict[str, NodeStyle],
    node_type: str,
) -> ResolvedNodeStyle:
    """Return resolved node style for the given type; fallback to 'default'."""
    style = node_styles.get(node_type) or node_styles.get("default") or NodeStyle()
    return style.resolve()


def get_link_style(
    link_styles: dict[str, LinkStyle],
    link_type: str = "default",
) -> ResolvedLinkStyle:
    """Return resolved link style for the given type; fallback to 'default'."""
    style = link_styles.get(link_type) or link_styles.get("default") or LinkStyle()
    return style.resolve()
