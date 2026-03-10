# Minify-HTML unit

Minifies HTML to reduce size: strips unnecessary whitespace and optionally minifies inline JS/CSS. Uses the `minify-html` library.

**Environment:** web (Python-only). Not exported to Node-RED/PyFlow.

**Optional dependency:** `pip install minify-html`

---

## API

- **Type name:** `minify_html`
- **Input ports:** `in` (Any) — HTML string (e.g. from browser unit)
- **Output ports:** `out` (Any) — minified HTML string

---

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `minify_js` | bool | False | Minify inline JavaScript. |
| `minify_css` | bool | False | Minify inline CSS. |
| `keep_comments` | bool | False | Keep HTML comments. |
| `keep_spaces_between_attributes` | bool | False | Preserve spaces between attributes. |
| `remove_processing_instructions` | bool | True | Remove processing instructions (e.g. `<?xml ...?>`). |

---

## Behavior

- If `minify-html` is not installed, output is an error message string.
- Input is passed through the library’s `minify()` with the given options; result is returned as the single output string.
