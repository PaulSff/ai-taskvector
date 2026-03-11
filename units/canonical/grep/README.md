# grep

Canonical unit: run grep to search in a **file path** or in **raw text** (e.g. Debug logs, code). Useful for the agent to inspect logs and code.

**Unit type:** `grep`

## Action (ProcessAgent)

The assistant can emit:

- `{ "action": "grep", "pattern": "error", "source": "log.txt" }` — search in file `log.txt` (e.g. written by a Debug unit).
- `{ "action": "grep", "pattern": "error", "source": "<inline text>" }` — search in the given string (e.g. pasted log or code).
- `{ "action": "grep", "pattern": "error" }` — no source; the unit uses its **input** (e.g. text from an upstream Debug unit).

Aliases: `command` or `regex` for the pattern; `path` for source when it is a file path.

## What is “source”?

| source            | Meaning | Example |
|-------------------|--------|--------|
| **Path**          | Path to a file on disk. If the string is an existing file path, grep runs on that file. | `"log.txt"`, `"mydata/out.log"` |
| **Text**          | Raw string content. If not an existing path, the unit runs grep on this text (via stdin). | Log content, code snippet, Debug output |
| **Omitted / input** | Use the unit’s input port `in` (path or text from upstream, e.g. Debug). | Connect Debug → grep; set only pattern in params/action. |

URL is not supported; use a separate step to fetch content and pass it as text or path.

## Interface

| Port / Param | Direction | Type | Description |
|--------------|-----------|------|-------------|
| **Input**    | in        | Any  | Optional path or raw text to search (e.g. from Debug). Used when params do not set source. |
| **Param**    | pattern / regex / command | str | Search pattern (required). `command` is an alias for agent use. |
| **Param**    | source / path / file | str | File path or inline text; overrides input when set. |
| **Param**    | options   | str  | Grep options (default `-n` for line numbers). |
| **Output**   | out       | Any  | Matching lines (stdout/stderr from grep). |
| **Output**   | error     | str  | Error message on timeout or subprocess failure; `None` on success. |

## Usage

- **Logs from Debug:** Debug writes to a file (e.g. `log.txt`). Agent emits `{ "action": "grep", "pattern": "error", "source": "log.txt" }`; a downstream unit or runner uses parser output to set the grep unit’s params and optionally pass the path.
- **Inline text:** Pass log or code as `source` string; the unit treats it as content and greps via stdin.
- **Upstream text:** Connect Debug (or any unit that outputs text) to grep’s `in`; set only `pattern` (e.g. from the grep action); source comes from the input.
