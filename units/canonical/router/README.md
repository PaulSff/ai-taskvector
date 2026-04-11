# Router

Demultiplexes a single **`data`** input to **one** output port (`out_0` … `out_7`, `default`, or `unmatched`) using **`params.routes`**. The same object is passed through on the chosen port only.

## Ports

| Input | Type | Description |
|-------|------|-------------|
| **data** | Any | Payload to inspect (e.g. `{ "action": "read_file", "path": "…" }`). |

Outputs: **`out_0` … `out_7`**, **`default`**, **`unmatched`**. Wire downstream only from the ports you use.

## `params.routes`

List of route objects, evaluated **in order**. First route that matches is used.

- **`port`**: must be one of the output port names above.
- **`default`**: if `true`, this route is used only when **no** earlier route matched (at most one default).
- **`all`**: list of rule dicts — **every** rule must match (AND).
- **`any`**: list of rule dicts — **at least one** must match (OR). Use when you do not set `all`, or prefer OR semantics.

A route with **neither** `all` nor `any` (and not `default`) **never matches** (avoids accidental “always on” routes).

### Rule dicts

Each rule should include **`field`** (dot path into `data`, e.g. `path` or `payload.path`) except when using only `exists` on the whole payload (set `field` to `""` and `exists` is interpreted on `data` via value from `_get_field` — prefer explicit `field`).

Supported keys (first applicable wins per rule object):

| Key | Meaning |
|-----|---------|
| **`equals`** | Field value must equal this (Python `==`). |
| **`equals_str`** | Compare as stripped strings. |
| **`ends_with`** | String field ends with suffix (case-insensitive). |
| **`starts_with`** | String field starts with prefix (case-insensitive). |
| **`contains`** | Substring (case-insensitive). |
| **`regex`** | `re.search` on stringified value. |
| **`exists`** | If `true`, field is present and not `None`. |

## Example (`read_file` → xlsx vs rest)

```json
{
  "type": "Router",
  "params": {
    "routes": [
      {
        "port": "out_0",
        "all": [{ "field": "path", "ends_with": ".xlsx" }]
      },
      { "port": "default", "default": true }
    ]
  }
}
```

If `action` must also be `read_file`:

```json
"all": [
  { "field": "action", "equals_str": "read_file" },
  { "field": "path", "ends_with": ".xlsx" }
]
```

## Behaviour

- **First match** among non-default routes.
- Then **`default`** if configured.
- Else **`unmatched`** receives `data` (still the same reference).

Downstream units only see an input on the **one** wired output that fired.
