from __future__ import annotations

from typing import cast

import flet as ft
from flet import Border, BorderSide
from markdown_it import MarkdownIt as _MarkdownIt
from markdown_it.token import Token

# ─── markdown-it-py block renderer ────────────────────────────────────────────
md_parser = _MarkdownIt("commonmark").enable("table")
_MONO_FAMILY = "Courier New"


def _md_inline_to_spans(
    tokens: list[Token],
    base_style: ft.TextStyle,
    *,
    bold: bool = False,
    italic: bool = False,
) -> list[ft.TextSpan]:
    spans: list[ft.TextSpan] = []
    i = 0
    n = len(tokens)

    while i < n:
        tok = tokens[i]

        if tok.type == "text":
            if bold or italic:
                style: ft.TextStyle = ft.TextStyle(
                    size=getattr(base_style, "size", None),
                    color=getattr(base_style, "color", None),
                    weight=ft.FontWeight.W_600 if bold else getattr(base_style, "weight", None),
                    italic=italic or bool(getattr(base_style, "italic", False)),
                    font_family=getattr(base_style, "font_family", None),
                )
            else:
                style = base_style
            spans.append(ft.TextSpan(tok.content, style=style))

        elif tok.type in ("softbreak", "hardbreak"):
            spans.append(ft.TextSpan("\n", style=base_style))

        elif tok.type == "strong_open":
            j = i + 1
            inner_strong: list[Token] = []
            while j < n and tokens[j].type != "strong_close":
                inner_strong.append(tokens[j])
                j += 1
            spans.extend(
                _md_inline_to_spans(inner_strong, base_style, bold=True, italic=italic)
            )
            i = j

        elif tok.type == "em_open":
            j = i + 1
            inner_em: list[Token] = []
            while j < n and tokens[j].type != "em_close":
                inner_em.append(tokens[j])
                j += 1
            spans.extend(
                _md_inline_to_spans(inner_em, base_style, bold=bold, italic=True)
            )
            i = j

        elif tok.type == "code_inline":
            spans.append(
                ft.TextSpan(
                    tok.content,
                    style=ft.TextStyle(
                        size=getattr(base_style, "size", None),
                        color=getattr(base_style, "color", ft.Colors.GREY_200),
                        font_family=_MONO_FAMILY,
                        weight=ft.FontWeight.W_600,
                        bgcolor=ft.Colors.GREY_900,
                    ),
                )
            )

        else:
            # children should also be list[Token] in markdown-it tokens
            children = getattr(tok, "children", None)
            if children:
                spans.extend(
                    _md_inline_to_spans(cast(list[Token], children), base_style, bold=bold, italic=italic)
                )
            elif getattr(tok, "content", ""):
                spans.append(ft.TextSpan(tok.content, style=base_style))

        i += 1

    return spans


def _md_table_block_to_ctrl(
    tokens: list[Token],
    i: int,
    text_style: ft.TextStyle,
    bubble_width: int | None,
) -> tuple[ft.Control, int]:
    """Render a table_open … table_close token slice into a DataTable Container."""
    n = len(tokens)
    i += 1  # skip table_open
    headers: list[ft.Text] = []
    rows: list[ft.DataRow] = []

    def inline_children(t: Token) -> list[Token]:
        # If your markdown-it Token type is untyped, this prevents "Any" / wrong list element types.
        ch = getattr(t, "children", None)
        if ch is None:
            return []
        return cast(list[Token], ch)

    if i < n and tokens[i].type == "thead_open":
        i += 1
        if i < n and tokens[i].type == "tr_open":
            i += 1
            while i < n and tokens[i].type != "tr_close":
                if tokens[i].type == "th_open" and i + 1 < n:
                    inline = tokens[i + 1]
                    spans = _md_inline_to_spans(inline_children(inline), text_style)
                    headers.append(ft.Text(spans=spans))
                    i += 3  # th_open, inline, th_close
                else:
                    i += 1
            if i < n and tokens[i].type == "tr_close":
                i += 1

        while i < n and tokens[i].type != "thead_close":
            i += 1
        if i < n:
            i += 1  # thead_close

    if i < n and tokens[i].type == "tbody_open":
        i += 1
        while i < n and tokens[i].type != "tbody_close":
            if tokens[i].type == "tr_open":
                i += 1
                cells: list[ft.DataCell] = []
                while i < n and tokens[i].type != "tr_close":
                    if tokens[i].type == "td_open" and i + 1 < n:
                        inline = tokens[i + 1]
                        spans = _md_inline_to_spans(inline_children(inline), text_style)
                        cells.append(ft.DataCell(ft.Text(spans=spans)))
                        i += 3
                    else:
                        i += 1
                if i < n and tokens[i].type == "tr_close":
                    i += 1
                rows.append(ft.DataRow(cells=cells))
            else:
                i += 1
        if i < n:
            i += 1  # tbody_close

    while i < n and tokens[i].type != "table_close":
        i += 1
    if i < n:
        i += 1  # table_close

    cols = [ft.DataColumn(label=h) for h in headers]
    tbl = ft.DataTable(
        expand=True,
        columns=cols,
        rows=rows,
        data_row_max_height=float("inf"),
        horizontal_margin=6,
        column_spacing=6,
    )
    return (
        ft.Container(
            content=tbl,
            padding=ft.padding.Padding.all(2),
            width=bubble_width,
            border=Border(bottom=BorderSide(0.6, ft.Colors.GREY_800)),
            bgcolor=ft.Colors.SURFACE,
        ),
        i,
    )


def _md_list_to_col(
    tokens: list[Token],
    i: int,
    text_style: ft.TextStyle,
    bubble_width: int | None,
    *,
    ordered: bool,
    indent: int,
) -> tuple[ft.Column, int]:
    """Render a bullet_list_open / ordered_list_open block into a Column of rows."""
    close_type = "ordered_list_close" if ordered else "bullet_list_close"
    i += 1  # skip list_open
    n = len(tokens)
    item_rows: list[ft.Control] = []
    item_num = 1

    while i < n and tokens[i].type != close_type:
        if tokens[i].type == "list_item_open":
            i += 1
            item_tokens: list[Token] = []
            depth = 1
            while i < n:
                if tokens[i].type == "list_item_open":
                    depth += 1
                elif tokens[i].type == "list_item_close":
                    depth -= 1
                    if depth == 0:
                        break
                item_tokens.append(tokens[i])
                i += 1

            if i < n:
                i += 1  # skip list_item_close

            body = md_blocks_to_controls(
                item_tokens, text_style, bubble_width, indent=indent + 1
            )
            bullet_w = 14 + indent * 10
            item_rows.append(
                ft.Row(
                    controls=[
                        ft.Text(
                            f"{item_num}." if ordered else "•",
                            style=text_style,
                            width=bullet_w,
                        ),
                        ft.Column(
                            controls=body or [ft.Text("", style=text_style)],
                            spacing=2,
                            expand=True,
                        ),
                    ],
                    vertical_alignment=ft.CrossAxisAlignment.START,
                    spacing=4,
                )
            )
            item_num += 1
        else:
            i += 1

    if i < n and tokens[i].type == close_type:
        i += 1

    return ft.Column(controls=item_rows, spacing=1, tight=True), i


def md_blocks_to_controls(
    tokens: list[Token],
    text_style: ft.TextStyle,
    bubble_width: int | None,
    *,
    indent: int = 0,
) -> list[ft.Control]:
    """Convert a flat markdown-it token list to Flet block controls."""
    controls: list[ft.Control] = []
    i = 0
    n = len(tokens)
    base_size = getattr(text_style, "size", 12) or 12

    def inline_children(t: Token | None) -> list[Token]:
        if t is None:
            return []
        ch = getattr(t, "children", None)
        if ch is None:
            return []
        return cast(list[Token], ch)

    while i < n:
        tok = tokens[i]

        if tok.type == "heading_open":
            level = int(tok.tag[1:]) if (tok.tag and tok.tag[1:].isdigit()) else 2
            inline = (
                tokens[i + 1]
                if i + 1 < n and tokens[i + 1].type == "inline"
                else None
            )
            spans = _md_inline_to_spans(inline_children(inline), text_style)

            h_size = base_size + max(0, 4 - level) * 2
            h_style = ft.TextStyle(
                size=h_size,
                weight=ft.FontWeight.W_700,
                color=getattr(text_style, "color", ft.Colors.GREY_400),
            )
            controls.append(
                ft.Text(
                    spans=spans,
                    style=h_style,
                    selectable=True,
                    no_wrap=False,
                    width=bubble_width,
                )
            )
            i += 3  # heading_open, inline, heading_close

        elif tok.type == "paragraph_open":
            inline = (
                tokens[i + 1]
                if i + 1 < n and tokens[i + 1].type == "inline"
                else None
            )
            spans = _md_inline_to_spans(inline_children(inline), text_style)
            controls.append(
                ft.Text(
                    spans=spans,
                    selectable=True,
                    no_wrap=False,
                    width=bubble_width,
                )
            )
            i += 3  # paragraph_open, inline, paragraph_close

        elif tok.type in ("bullet_list_open", "ordered_list_open"):
            col, i = _md_list_to_col(
                tokens,
                i,
                text_style,
                bubble_width,
                ordered=(tok.type == "ordered_list_open"),
                indent=indent,
            )
            controls.append(col)

        elif tok.type == "table_open":
            ctrl, i = _md_table_block_to_ctrl(tokens, i, text_style, bubble_width)
            controls.append(ctrl)

        elif tok.type == "hr":
            controls.append(ft.Divider(height=1, color=ft.Colors.GREY_800))
            i += 1

        elif tok.type == "inline":
            spans = _md_inline_to_spans(inline_children(tok), text_style)
            if spans:
                controls.append(
                    ft.Text(
                        spans=spans,
                        selectable=True,
                        no_wrap=False,
                        width=bubble_width,
                    )
                )
            i += 1

        else:
            i += 1

    return controls
