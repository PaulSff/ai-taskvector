# CalendarICS Unit (CalendarICS)

Manage iCalendar (`.ics`) calendars stored on disk via actions:
- `create_calendar`
- `get_all_calendars`
- `check_availability`
- `reserve`
- `cancel`

This unit uses iCalendar VEVENTs:
- **Busy events**: any VEVENT whose `CLASS` is **not** `"PRIVATE"` (including missing `CLASS`).
- **Private blocks**: VEVENTs with `CLASS == "PRIVATE"`.
- Time arithmetic is performed with tz-aware datetimes using the configured `timezone`.
- Interval conflicts use **half-open semantics**: `[start, end)` (an event ending exactly when another starts does not overlap).

---

## Inputs / Outputs

### Input port
- `("input", Any)`: an object with shape:
  - `{ "action": <string>, ... }`

### Output ports
- `("data", Any)`
- `("error", str)`

On success, `data["ok"]` is `true`.
On failure, `data["ok"]` is `false` and `data["error"]` contains details.

---

## Unit Parameters (configuration)

Required:
- `calendar_dir`: directory path where `.ics` files are stored.

Optional:
- `timezone`: IANA tz name (default: `"UTC"`)
- `horizon_days`: used by `create_calendar` to generate default private blocks (default: `30`)
- `slot_size_min`: minutes for snapping in `check_availability` and alignment checks in `reserve` (default: `30`)
- `default_private_start`: `"HH:MM"` or `"HH:MM:SS"` (default: `"00:00"`)
- `default_private_end`: `"HH:MM"` or `"HH:MM:SS"` (default: `"08:00"`)
- `reserve_enforce_slot_alignment`: if `true`, `reserve` requires `from/to` to align to `slot_size_min` boundaries (default: `true`)

---

## iCalendar storage conventions

When you call `create_calendar`, the unit creates an empty calendar and **seeds default PRIVATE blocks** for each day in the next `horizon_days` starting from “today” in the configured timezone.

Each seeded PRIVATE block is:
- `CLASS: PRIVATE`
- `summary: "Private time"`
- `uid: "private-YYYY-MM-DD@default"`

Reservation events created by `reserve`:
- are added as VEVENTs with `DTSTART/DTEND`
- include `summary` (default `"Reserved"` unless `event_name` is provided)
- **do not set `CLASS`**, so they are treated as **busy**.

Cancellation removes VEVENTs by matching UID.

---

## Actions

### 1) `create_calendar`

Creates a calendar file and seeds default PRIVATE blocks for the configured future horizon.

#### Request (input)
```json
{
  "action": "create_calendar",
  "file_name": "calendar.ics",
  "availability": []
}
```

- `file_name` is optional; defaults to "calendar.ics".
- `availability` may be provided but is not stored in the calendar. It is only relevant to `check_availability`.

#### Response (data)

json

```json
{
  "ok": true,
  "path": "/full/path/to/calendar.ics",
  "status": "created"
}
```

### 2) get_all_calendars

Lists all `.ics` files in `calendar_dir`.

#### Request (input)

```json
{
  "action": "get_all_calendars"
}
```

#### Response (data)

```json
{
  "ok": true,
  "calendars": ["a.ics", "b.ics"]
}
```

### 3) check_availability

Computes free slots in the configured availability windows, subtracting:

  1. busy VEVENTs (all non-PRIVATE),
  2. PRIVATE blocks.
Optionally returns scheduled events as part of the response.

#### Request (input)

```json
{
  "action": "check_availability",
  "cal_file_name": "calendar.ics",
  "period_d": 30,
  "include_scheduled_events": false,

  "availability": [
    {
      "periodic": {
        "from_day_of_week": "mon",
        "to_day_of_week": "fri",
        "from_time": "09:00",
        "to_time": "17:00"
      }
    },
    {
      "static": {
        "from_date": "2026-08-01",
        "to_date": "2026-08-15",
        "from_time": "10:00",
        "to_time": "14:30"
      }
    }
  ]
}
```

Notes:

- `period_d` is optional; default `30` (used as the horizon length for generating free slots).
- `include_scheduled_events` is optional; default `false`.
- `availability` is optional:
  - If omitted, it is treated as `[]` (so only busy subtraction applies after expanding availability—result is typically empty because there are no availability windows to subtract from).
- You may also provide availability via unit params (`params["availability"]`); this implementation primarily uses the `action_obj["availability"]` / `params["availability"]` fallback logic.

##### Availability entries

A) periodic

```json
{
  "periodic": {
    "from_day_of_week": "mon",
    "to_day_of_week": "sun",
    "from_time": "HH:MM",
    "to_time": "HH:MM"
  }
}
```
- Weekday range is inclusive.
- Wrap-around is allowed (e.g., from `fri` to `tue`).

B) static

```json
{
  "static": {
    "from_date": "YYYY-MM-DD",
    "to_date": "YYYY-MM-DD",
    "from_time": "HH:MM",
    "to_time": "HH:MM"
  }
}
```
- Both dates are inclusive.

Time windows that “overnight” (end <= start) are treated as ending the next day.


#### Response (data)

```json 
{
  "ok": true,
  "slot_size_min": 30,
  "free_slots": [
    { "from": "2026-08-20T09:00:00+00:00", "to": "2026-08-20T12:00:00+00:00" }
  ],
  "scheduled_events": [
    {
      "uid": "evt-...@local",
      "summary": "Reserved",
      "class": "PRIVATE",
      "dtstart": "2026-08-20T00:00:00+00:00",
      "dtend": "2026-08-20T08:00:00+00:00",
      "properties": {
        "someProperty": "someValue"
      }
    }
  ]
}
```

Rules:

- Output `free_slot`s are snapped to `slot_size_min`:
  - start is snapped up
  - end is snapped down
  - segments that become invalid (end <= start) are dropped.
- If `include_scheduled_events` is `false`, `scheduled_events` is omitted.


### 4) reserve

Creates a VEVENT for the requested interval if it:

  - has `end > start`
  - does not overlap any PRIVATE block
  - does not overlap any non-PRIVATE VEVENT
Optionally enforces slot alignment to `slot_size_min.`


#### Request (input)

```json
{
  "action": "reserve",
  "cal_file_name": "calendar.ics",
  "from": { "date": "2026-08-20", "time": "09:00" },
  "to":   { "date": "2026-08-20", "time": "10:00" },

  "event_name": "Team meeting",
  "properties": { "X-MYFIELD": "value" },

  "reserve_enforce_slot_alignment": true
}
```

Notes:

  - `from/to.time` may be `"HH:MM"` or `"HH:MM:SS"` in the unit’s parser.
  - `reserve_enforce_slot_alignment` is optional:
    - if not provided in the action, it uses the unit param `reserve_enforce_slot_alignment` (default `true`).

  Alignment:

When enforced, both `from` and `to` must fall exactly on `slot_size_min` boundaries relative to the epoch in the configured timezone.


#### Response (data)

```json
{
  "ok": true,
  "status": "reserved",
  "calendar_path": "/full/path/to/calendar.ics",
  "event_id": "evt-1720000000000@local"
}
```

### 5) cancel

Removes a previously reserved event by UID.

```json
{
  "action": "cancel",
  "cal_file_name": "calendar.ics",
  "event_id": "evt-1720000000000@local"
}
```

#### Response (data)

If found:

```json
{
  "ok": true,
  "status": "cancelled",
  "calendar_path": "/full/path/to/calendar.ics"
}
```

#### If not found:

```json
{
  "ok": false,
  "status": "not_found",
  "calendar_path": "/full/path/to/calendar.ics"
}
```

## End-to-end examples

### Example A: Create calendar, then check availability

```json
// 1) create
{
  "action": "create_calendar",
  "file_name": "calendar.ics"
}
```

```json
// 2) check availability
{
  "action": "check_availability",
  "cal_file_name": "calendar.ics",
  "period_d": 30,
  "include_scheduled_events": false,
  "availability": [
    {
      "periodic": {
        "from_day_of_week": "mon",
        "to_day_of_week": "fri",
        "from_time": "09:00",
        "to_time": "17:00"
      }
    }
  ]
}
```

### Example B: Reserve a slot

Assuming `slot_size_min = 30` and enforcement is enabled:

```json
{
  "action": "reserve",
  "cal_file_name": "calendar.ics",
  "from": { "date": "2026-08-20", "time": "09:00" },
  "to":   { "date": "2026-08-20", "time": "10:00" },
  "event_name": "Interview"
}
```

### Example C: Cancel a reservation

```json
{
  "action": "cancel",
  "cal_file_name": "calendar.ics",
  "event_id": "evt-1720000000000@local"
}
```
