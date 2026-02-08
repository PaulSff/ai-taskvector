"""
Configurable styling for workflow graph nodes and links (edges + arrows).
Keys: node type (unit.type, e.g. Source, Valve) and link type (e.g. default).
"""
from __future__ import annotations

from dataclasses import dataclass

import flet as ft


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

    def resolve(self) -> ResolvedNodeStyle:
        return ResolvedNodeStyle(
            bgcolor=_resolve_color(self.bgcolor),
            border_color=_resolve_color(self.border_color),
            text_color=_resolve_color(self.text_color),
            text_secondary_color=_resolve_color(self.text_secondary_color),
            border_radius=self.border_radius,
            bg_highlight=_resolve_color(self.bg_highlight),
            border_highlight=_resolve_color(self.border_highlight),
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


# Default styles per node type and link type
DEFAULT_NODE_STYLES: dict[str, NodeStyle] = {
    "default": NodeStyle(),
    "Source": NodeStyle(bgcolor="grey_800", border_color="green_700"),
    "Valve": NodeStyle(bgcolor="grey_800", border_color="orange_700"),
    "Tank": NodeStyle(bgcolor="grey_800", border_color="blue_700"),
    "Sensor": NodeStyle(bgcolor="grey_800", border_color="teal_700"),
}

DEFAULT_LINK_STYLES: dict[str, LinkStyle] = {
    "default": LinkStyle(),
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
