# Debug unit

Listens on input port `data` (Any), appends the received value to a log file, and forwards the same value to output port `data`.

- **Input:** `data` (Any) — whatever is sent from the upstream unit.
- **Output:** `data` (Any) — pass-through of the input.
- **Params:** `log_path` (optional) — path to the log file; default `log.txt` (relative to process cwd).

Log lines are prefixed with a UTC timestamp. Values are serialized as JSON for dict/list, otherwise as string or repr.
