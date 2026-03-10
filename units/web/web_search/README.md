# Web search unit

Queries DuckDuckGo (or compatible) and outputs search results as plain text: title, URL, and snippet per result. Suitable for LLM context (e.g. Workflow Designer web_search action).

**Environment:** web (Python-only). Not exported to Node-RED/PyFlow.

**Optional dependency:** `pip install duckduckgo-search` (or `ddgs`)

---

## API

- **Type name:** `web_search`
- **Input ports:** `in` (Any) — optional; query can come from params instead
- **Output ports:** `out` (Any) — plain text: one block per result (`title`, `URL`, `snippet`), not HTML

---

## Parameters

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `query` | str | — | Search query. If not set, first input value is used. |
| `q` | str | — | Alias for `query`. |
| `max_results` | int | 10 | Number of results (clamped 1–20). |

---

## Output format

Plain text, one result per block:

```
Title of result
  https://example.com/page
  Snippet or description text.
```

No HTML; safe to pass directly to an LLM or merge into a follow-up turn.

---

## Standalone helper

`run_web_search(query: str, max_results: int = 10) -> str` — runs the same logic without registering the unit (e.g. for Workflow Designer web_search action).
