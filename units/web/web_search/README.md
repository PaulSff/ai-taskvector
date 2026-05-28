# Web search unit

Queries DuckDuckGo (or compatible) and outputs search results as plain text: title, URL, and snippet per result. Suitable for LLM context (e.g. Workflow Designer web_search action).

**Environment:** web (Python-only). Not exported to Node-RED/PyFlow.

**Dependency:** `pip install ddgs`

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
| `max_results` | int | 10 | Number of results (clamped 1–100) |
| `region` | str | us-en | Optional region string | us-en, uk-en, ru-ru, etc. |
| `safesearch` | str |'moderate' | Level of moderation of search results ('moderate'/'off'/'strict') |
| `timelimit` | str | None | Optional time limit for results (d, w, m, y) |
| `page` | int | 1 | Page of results |
| `backend` | str | 'auto' | A single or comma-delimited backend (ddgs backend arg) |

---

## Input example

```json
{
"data": "What are the latest breakthroughs in AI agent"
}
```

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
