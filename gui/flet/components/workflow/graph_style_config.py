"""
Configurable styling for workflow graph nodes and links (edges + arrows).
Keys: node type (unit.type, e.g. Source, Valve) and link type (e.g. default).
"""
from __future__ import annotations

from dataclasses import dataclass

import flet as ft


# Default node dimensions when not overridden per type
DEFAULT_NODE_WIDTH = 160
DEFAULT_NODE_HEIGHT = 68

# Port layout (input/output dots on node left/right)
PORT_ROW_HEIGHT = 16
PORT_DOT_RADIUS = 4
# Vertical margin from first/last port dot to node top/bottom so dots stay inside the border
PORT_EDGE_MARGIN = 4
# Inner padding of the node container (must match usage in graph_canvas for port Y offset)
NODE_PADDING = 8

# Standard border colors for undefined/imported types (e.g. Node-RED "function", "inject").
# Same type always gets the same color (by hash). Must not duplicate known types:
# Source=green, Valve=orange, Tank=blue, Sensor=teal, RLAgent=purple, LLMAgent=indigo,
# StepDriver=amber, StepRewards=teal, Join=indigo, Switch=orange, Split=purple, HttpIn=cyan, HttpResponse=grey.
UNDEFINED_TYPE_PALETTE: tuple[str, ...] = (
    "red_700",
    "pink_600",
    "lime_700",
    "deep_orange_600",
    "light_blue_600",
    "brown_700",
    "lime_600",
    "yellow_700",
    "rose_600",
    "light_green_600",
    "red_600",
    "pink_500",
)


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
    arrow_half_width: int = 4
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
        width=168,
        height=66,
        icon="play_arrow",
    ),
    "StepRewards": NodeStyle(
        bgcolor="grey_800",
        border_color="teal_600",
        border_highlight="teal_400",
        width=168,
        height=82,
        icon="emoji_events",
    ),
    "Join": NodeStyle(
        bgcolor="grey_800",
        border_color="indigo_600",
        border_highlight="indigo_400",
        width=120,
        height=166,
        icon="merge_type",
    ),
    "Merge": NodeStyle(
        bgcolor="grey_800",
        border_color="teal_600",
        border_highlight="teal_400",
        width=120,
        height=166,
        icon="merge",
    ),
    "Aggregate": NodeStyle(
        bgcolor="grey_800",
        border_color="teal_600",
        border_highlight="teal_400",
        width=120,
        height=166,
        icon="merge",
    ),
    "Prompt": NodeStyle(
        bgcolor="grey_800",
        border_color="amber_600",
        border_highlight="amber_400",
        width=120,
        height=100,
        icon="description",
    ),
    "Switch": NodeStyle(
        bgcolor="grey_800",
        border_color="orange_600",
        border_highlight="orange_400",
        width=136,
        height=168,
        icon="account_tree",
    ),
    "Split": NodeStyle(
        bgcolor="grey_800",
        border_color="purple_600",
        border_highlight="purple_400",
        width=110,
        height=160,
        icon="call_split",
    ),
    "HttpIn": NodeStyle(
        bgcolor="grey_800",
        border_color="cyan_600",
        border_highlight="cyan_400",
        width=140,
        height=48,
        icon="input",
    ),
    "HttpResponse": NodeStyle(
        bgcolor="grey_800",
        border_color="grey_500",
        border_highlight="grey_400",
        width=172,
        height=54,
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


def _undefined_type_style(node_type: str) -> NodeStyle:
    """Return a NodeStyle for an unknown type using a deterministic color from UNDEFINED_TYPE_PALETTE."""
    idx = hash(node_type) % len(UNDEFINED_TYPE_PALETTE)
    border = UNDEFINED_TYPE_PALETTE[idx]
    # Use a lighter shade for highlight when possible (e.g. amber_600 -> amber_400)
    highlight = border.replace("_700", "_400").replace("_600", "_400").replace("_500", "_400")
    if highlight == border:
        highlight = "blue_400"
    return NodeStyle(
        bgcolor="grey_800",
        border_color=border,
        border_highlight=highlight,
        text_color="white",
        text_secondary_color="grey_400",
    )


def get_node_style(
    node_styles: dict[str, NodeStyle],
    node_type: str,
) -> ResolvedNodeStyle:
    """Return resolved node style for the given type. Known types use config; unknown types (e.g. imported) get a deterministic color from UNDEFINED_TYPE_PALETTE."""
    if node_type in node_styles:
        return node_styles[node_type].resolve()
    # Unknown type: use standard palette so different imported types get distinct colors
    return _undefined_type_style(node_type).resolve()


def get_link_style(
    link_styles: dict[str, LinkStyle],
    link_type: str = "default",
) -> ResolvedLinkStyle:
    """Return resolved link style for the given type; fallback to 'default'."""
    style = link_styles.get(link_type) or link_styles.get("default") or LinkStyle()
    return style.resolve()


# Highlight color for edge hover (same as default LinkStyle); edges keep this on hover instead of node border_highlight
EDGE_HOVER_HIGHLIGHT_COLOR = "blue_400"

# Comment stickers: distinct shape (no ports, no wiring), sticky-note style for graph comments
COMMENT_STICKER_WIDTH = 140
COMMENT_STICKER_HEIGHT = 72
COMMENT_STICKER_BG = "amber_100"  # Light sticky-note tint
COMMENT_STICKER_BORDER = "amber_700"
COMMENT_STICKER_TEXT = "grey_900"
COMMENT_STICKER_SECONDARY = "grey_700"
COMMENT_STICKER_BORDER_RADIUS = 6
COMMENT_STICKER_MAX_LINES = 3  # Truncate info to this many lines in preview
COMMENT_STICKER_LINE_LENGTH = 24  # Approximate chars per line for truncation

# Node chat-drag handle (small button in node corner).
NODE_CHAT_DRAG_ICON = "chat_bubble_outline"
NODE_CHAT_DRAG_ICON_SIZE = 14
NODE_CHAT_DRAG_TOOLTIP = "Drag to assistants chat"
NODE_CHAT_DRAG_ICON_COLOR = "blue_200"
NODE_CHAT_DRAG_ICON_OPACITY = 0.85
NODE_CHAT_DRAG_BUTTON_PADDING = 2
NODE_CHAT_DRAG_CONTAINER_WIDTH = 30
NODE_CHAT_DRAG_CONTAINER_HEIGHT = 30
NODE_CHAT_DRAG_CONTAINER_TOP = -6
NODE_CHAT_DRAG_CONTAINER_LEFT_INSET = 28


def get_link_style_from_node_border(
    node_styles: dict[str, NodeStyle],
    node_type: str,
    *,
    link_dimensions: LinkStyle | None = None,
) -> ResolvedLinkStyle:
    """Return a link style that uses the given node type's border color for the edge line and arrow.
    Used to paint edges in the same color as the source unit's border.
    Hover highlight is always EDGE_HOVER_HIGHLIGHT_COLOR (blue) as before."""
    dims = link_dimensions or LinkStyle()
    node_style = get_node_style(node_styles, node_type)
    highlight = _resolve_color(EDGE_HOVER_HIGHLIGHT_COLOR)
    return ResolvedLinkStyle(
        edge_paint=ft.Paint(
            stroke_width=dims.stroke_width,
            color=node_style.border_color,
            style=ft.PaintingStyle.STROKE,
        ),
        arrow_paint=ft.Paint(style=ft.PaintingStyle.FILL, color=node_style.border_color),
        edge_paint_highlight=ft.Paint(
            stroke_width=dims.stroke_width,
            color=highlight,
            style=ft.PaintingStyle.STROKE,
        ),
        arrow_paint_highlight=ft.Paint(style=ft.PaintingStyle.FILL, color=highlight),
        arrow_length=dims.arrow_length,
        arrow_half_width=dims.arrow_half_width,
    )
