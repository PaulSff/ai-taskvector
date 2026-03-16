# RuntimeLabel

Detect runtime label and native flag from a process graph. Wraps `core.normalizer.runtime_detector.runtime_label` and `is_canonical_runtime`.

- **Input:** `graph` (dict or ProcessGraph).
- **Output:** `label` (str), `is_native` (bool).

Used by the GUI and chat so runtime detection is done via workflow instead of direct Core dependency.
