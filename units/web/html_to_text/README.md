# HTML-to-text unit

Converts HTML to plain text in a Markdown-style format. Uses the `html2text` library when available; otherwise returns the input unchanged. Suited for feeding HTML (e.g. from the **browser** unit) to LLMs or other text consumers.

**Environment:** web (Python-only). Not exported to Node-RED/PyFlow.

**Optional dependency:** `pip install html2text`

---

## API

- **Type name:** `html_to_text`
- **Input ports:** `in` (Any) — HTML string (e.g. from browser unit)
- **Output ports:** `out` (Any) — plain text (Markdown-style when html2text is installed)

---

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `ignore_links` | bool | False | When True, html2text will not emit link markup. |

---

## Behavior

- If `html2text` is installed: HTML is converted to Markdown-style plain text.
- If not installed: input HTML is returned as-is (no conversion).

For strict “HTML → plain text” extraction (no Markdown), use the **beautifulsoup** unit with `mode="text"` instead.
