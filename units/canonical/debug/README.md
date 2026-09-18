# Debug unit

Listens on input port `data` (Any), appends the received value to a log file, and forwards the same value to output port `data`.

- **Input:** `data` (Any) — whatever is sent from the upstream unit.
- **Output:** 
    - `data` (Any) — pass-through of the input.
    - `error` (str) — contains the error message if logging fails (e.g., OSError), otherwise None.
- **Params:** `log_path` (optional) — path to the log file; default `workflow.log` (relative to process cwd).

Log lines are prefixed with a UTC timestamp. Values are serialized as JSON for dict/list, otherwise as string or repr. Special cases: empty strings are logged as `(empty)`, and dictionaries containing only empty/None values are logged as `(no errors)`.
