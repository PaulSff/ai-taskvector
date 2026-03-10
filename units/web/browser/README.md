# Browser unit

Fetches a URL via HTTP GET and outputs the raw response body (e.g. HTML). No JavaScript execution; for full browser behavior use an external tool (e.g. Playwright).

**Environment:** web (Python-only). Not exported to Node-RED/PyFlow.

---

## API

- **Type name:** `browser`
- **Input ports:** `in` (Any) — optional; URL can come from params instead
- **Output ports:** `out` (Any) — raw response body as string (e.g. HTML)

---

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `url` | str | — | URL to fetch. If not set, first input value is used. |
| `timeout` | float | 15 | Request timeout in seconds (clamped 1–60). |

---

## Behavior

- Uses `requests` if available, otherwise `urllib.request`.
- Response body is capped at 1 MB; excess is truncated with a note.
- Does **not** extract text from HTML; chain with the **beautifulsoup** or **html_to_text** unit for that.
- On error (network, timeout, etc.), output is an error message string.

---

## Standalone helper

`fetch_url(url: str, timeout: float = 15) -> str` — runs the same logic without registering the unit (e.g. for Workflow Designer browse action: `fetch_url(url)` then `html_to_text(html)`).
