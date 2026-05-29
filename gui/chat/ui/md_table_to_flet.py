"""
This component converts markdown tables into Flet native tables layout
Requires: pip install markdown-it-py
"""

from typing import List

import flet as ft
from markdown_it import MarkdownIt

md = MarkdownIt("commonmark").enable("table")


def _render_inline_tokens_to_spans(inline_tokens, text_style):
    spans = []
    mono = "monospace"
    i = 0
    while i < len(inline_tokens):
        t = inline_tokens[i]
        if t.type == "text":
            spans.append(ft.TextSpan(t.content, style=text_style))
        elif t.type == "strong_open":
            j = i + 1
            content = ""
            while j < len(inline_tokens) and inline_tokens[j].type != "strong_close":
                content += getattr(inline_tokens[j], "content", "")
                j += 1
            spans.append(
                ft.TextSpan(content, style=ft.TextStyle(weight=ft.FontWeight.W_700))
            )
            i = j
        elif t.type == "code_inline":
            spans.append(
                ft.TextSpan(
                    t.content,
                    style=ft.TextStyle(
                        font_family=mono,
                        weight=ft.FontWeight.W_600,
                        bgcolor=ft.Colors.GREY_900,
                    ),
                )
            )
        else:
            if getattr(t, "content", None):
                spans.append(ft.TextSpan(t.content, style=text_style))
        i += 1
    return spans


def markdown_table_to_datatable(
    md_text: str, text_style: ft.TextStyle
) -> List[ft.DataTable]:
    tokens = md.parse(md_text)
    tables: List[ft.DataTable] = []
    i = 0
    n = len(tokens)
    while i < n:
        if tokens[i].type == "table_open":
            i += 1
            headers = []
            # thead
            if i < n and tokens[i].type == "thead_open":
                i += 1
                if i < n and tokens[i].type == "tr_open":
                    i += 1
                    while i < n and tokens[i].type != "tr_close":
                        if tokens[i].type == "th_open" and i + 1 < n:
                            inline = tokens[i + 1]
                            spans = _render_inline_tokens_to_spans(
                                getattr(inline, "children", []), text_style
                            )
                            headers.append(ft.Text(spans=spans))
                            i += 3
                        else:
                            i += 1
                    if i < n and tokens[i].type == "tr_close":
                        i += 1
                while i < n and tokens[i].type != "thead_close":
                    i += 1
                if i < n and tokens[i].type == "thead_close":
                    i += 1
            # tbody
            rows: List[ft.DataRow] = []
            if i < n and tokens[i].type == "tbody_open":
                i += 1
                while i < n and tokens[i].type != "tbody_close":
                    if tokens[i].type == "tr_open":
                        i += 1
                        cells: List[ft.DataCell] = []
                        while i < n and tokens[i].type != "tr_close":
                            if tokens[i].type == "td_open" and i + 1 < n:
                                inline = tokens[i + 1]
                                spans = _render_inline_tokens_to_spans(
                                    getattr(inline, "children", []), text_style
                                )
                                cells.append(ft.DataCell(ft.Text(spans=spans)))
                                i += 3
                            else:
                                i += 1
                        if i < n and tokens[i].type == "tr_close":
                            i += 1
                        rows.append(ft.DataRow(cells=cells))
                    else:
                        i += 1
                if i < n and tokens[i].type == "tbody_close":
                    i += 1
            # skip to table_close
            while i < n and tokens[i].type != "table_close":
                i += 1
            if i < n and tokens[i].type == "table_close":
                i += 1
            cols = [ft.DataColumn(label=h) for h in headers]
            tables.append(
                ft.DataTable(
                    expand=True,
                    columns=cols,
                    rows=rows,
                    data_row_max_height=float("inf"),
                    horizontal_margin=6,
                    column_spacing=6,
                )
            )
            continue
        i += 1
    return tables


__all__ = ["markdown_table_to_datatable", "_render_inline_tokens_to_spans"]
