# BeautifulSoup unit

Parses HTML and extracts content as plain text, links, tables, or markup. Typical use: after the **browser** unit (e.g. Browser → BeautifulSoup to get page text).

**Environment:** web (Python-only). Not exported to Node-RED/PyFlow.

**Optional dependency:** `pip install beautifulsoup4`

---

## API

- **Type name:** `beautifulsoup`
- **Input ports:** `in` (Any) — HTML string (e.g. from browser unit)
- **Output ports:** `out` (Any) — extracted content as string

---

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `mode` | str | `"text"` | `"text"` \| `"links"` \| `"tables"` \| `"markup"`. What to extract. |
| `selector` | str | — | CSS selector to restrict to a subtree (optional). |
| `css_selector` | str | — | Alias for `selector`. |
| `limit` | int | 0 | For `links` or `tables`, max number to return; 0 = no limit. |

---

## Modes

- **text** — `get_text()` on the root (or selected node); newline-separated, stripped.
- **links** — All `<a href="...">` as `href\tlink_text` (or just `href`) per line.
- **tables** — Table rows as tab-separated cells; tables separated by blank lines.
- **markup** — Prettified HTML string.

---

## Standalone helper

`html_to_text(html: str, mode: str = "text", **params) -> str` — runs the same logic without registering the unit (e.g. browse action: `fetch_url(url)` then `html_to_text(html, mode="text")`).
