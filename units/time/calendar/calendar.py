"""
CalendarICS unit
=================

Purpose
-------
Manage iCalendar (.ics) calendars via actions:

- action="calendar", method="create_calendar": creates an .ics file and seeds default PRIVATE blocks for a future horizon
- action="calendar", method="check_availability": computes free slots given an availability policy, subtracting busy events and PRIVATE blocks
- action="calendar", method="reserve": creates a VEVENT for a requested interval if it doesn't overlap PRIVATE or any existing busy VEVENT
- action="calendar", method="cancel": removes a VEVENT by UID

Calendar model assumptions
---------------------------
- Busy events are any VEVENT whose CLASS is not "PRIVATE".
- Private blocks are VEVENT with CLASS == "PRIVATE".
- All time arithmetic is done in the configured `timezone` and treated as tz-aware datetimes.
- Interval math uses half-open semantics: [start, end).

Ports
-----
Input port:
- ("input", Any): an object with shape {"action": "calendar", "method": <str>, ...}

Output ports:
- ("data", Any)
- ("error", str)

Params (unit configuration)
---------------------------
Required:
- calendar_dir: path-like (directory where .ics files are stored)

Optional:
- timezone: IANA tz name, default "UTC"
- horizon_days: used only by create_calendar, default 30
- slot_size_min: slot length in minutes for check_availability snapping and reserve alignment checks, default 30
- default_private_start: "HH:MM" (or "HH:MM:SS"), default "00:00"
- default_private_end: "HH:MM" (or "HH:MM:SS"), default "08:00"
- reserve_enforce_slot_alignment: bool, default true
  (if true, reserve fails when requested from/to are not aligned to slot boundaries)

Action input shapes
--------------------

1) create_calendar
------------------
inputs["input"] object:
{
  "action": "calendar",
  "method": "create_calendar",
  "file_name": "calendar.ics"   // optional (defaults to "calendar.ics")
  "availability": [...]         // accepted but not stored; availability is used by check_availability
}

Return:
{
  "ok": true,
  "path": "<full path to created .ics>",
  "status": "created"
}

2) get_all_calendars
--------------------
inputs["input"] object:
{
  "action": "calendar",
  "method": "get_all_calendars"
}

Return:
{
  "ok": true,
  "calendars": ["a.ics", "b.ics", ...]
}

3) check_availability
----------------------
inputs["input"] object:
{
  "action": "calendar",
  "method": "check_availability",
  "cal_file_name": "calendar.ics",
  "period_d": 30,                         // optional horizon in days, default 30
  "include_scheduled_events": false,    // optional, default false
  "availability": [...]                  // optional; alternatively provide params["availability"]
}

Availability shape (list of entries):
Each entry is one of:
A) {"periodic": {
      "from_day_of_week": "mon|tue|...|sun",
      "to_day_of_week":   "mon|tue|...|sun",   // inclusive weekday range; wrap-around allowed
      "from_time": "HH:MM" | "HH:MM:SS",
      "to_time":   "HH:MM" | "HH:MM:SS"
   }}

B) {"static": {
      "from_date": "YYYY-MM-DD",
      "to_date":   "YYYY-MM-DD",       // inclusive
      "from_time": "HH:MM" | "HH:MM:SS",
      "to_time":   "HH:MM" | "HH:MM:SS"
   }}

Return:
{
  "ok": true,
  "slot_size_min": <int>,
  "free_slots": [
     {"from": "<iso datetime with tz>", "to": "<iso datetime with tz>"},
     ...
  ],
  "scheduled_events": [...] // only when include_scheduled_events=true
}

4) reserve
-----------
inputs["input"] object:
{
  "action": "calendar",
  "method": "reserve",
  "cal_file_name": "calendar.ics",
  "from": {"date": "YYYY-MM-DD", "time": "HH:MM" | "HH:MM:SS"},
  "to":   {"date": "YYYY-MM-DD", "time": "HH:MM" | "HH:MM:SS"},
  "event_name": "Team meeting",           // optional
  "properties": { "X-MYFIELD": "value", ... } // optional custom VEVENT fields
}

Validation:
- requested interval must have end > start
- must not overlap any PRIVATE block
- must not overlap any non-PRIVATE VEVENT
- if reserve_enforce_slot_alignment==true, from/to must align to slot_size_min boundaries

Return:
{
  "ok": true,
  "status": "reserved",
  "calendar_path": "<path>",
  "event_id": "<uid>"
}

5) cancel
---------
inputs["input"] object:
{
  "action": "calendar",
  "method": "cancel",
  "cal_file_name": "calendar.ics",
  "event_id": "<uid from reserve>"
}

Return:
{
  "ok": true/false,
  "status": "cancelled" | "not_found",
  "calendar_path": "<path>"
}
"""


from __future__ import annotations


from datetime import datetime, date, time, timedelta
from pathlib import Path
from typing import Any

from zoneinfo import ZoneInfo

from icalendar import Calendar, Event

from units.registry import UnitSpec, register_unit

# =========================
# Ports
# =========================
CAL_INPUT_PORTS = [("input", "Any")]
CAL_OUTPUT_PORTS = [("data", "Any"), ("error", "str")]

# =========================
# Params (unit configuration)
# =========================
# Required/expected in params:
# - calendar_dir: path
# Optional params:
# - horizon_days: used for generating default private blocks and for create-calendar-created calendar content (default 30)
# - slot_size_min: minutes for snapping (default 30)
# - timezone: tz name for interpreting/recording times (default "UTC")
# - default_private_start: "HH:MM" (default "00:00")
# - default_private_end:   "HH:MM" (default "08:00")
#
# NOTE: availability/action inputs use "UTC date:from.., to.." per your spec. This unit uses the configured timezone
# (default UTC) for DT values written into the .ics.


# =========================
# Utilities: time + intervals
# =========================
def _parse_hhmm(s: str) -> time:
    # Accept "HH:MM" or "HH:MM:SS"
    s = (s or "").strip()
    if not s:
        raise ValueError("time string empty")
    dt = datetime.fromisoformat(f"2000-01-01T{s}")
    return dt.time()


def _dow_to_int(d: str) -> int:
    # Mon=0 ... Sun=6
    m = {
        "mon": 0,
        "monday": 0,
        "tue": 1,
        "tues": 1,
        "tuesday": 1,
        "wed": 2,
        "wednesday": 2,
        "thu": 3,
        "thur": 3,
        "thurs": 3,
        "thursday": 3,
        "fri": 4,
        "friday": 4,
        "sat": 5,
        "saturday": 5,
        "sun": 6,
        "sunday": 6,
    }
    key = (d or "").strip().lower()
    if key not in m:
        raise ValueError(f"Unknown day_of_week: {d!r}")
    return m[key]


def _overlaps(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> bool:
    # half-open intervals [start, end)
    return a_start < b_end and b_start < a_end


def _clip(a_start: datetime, a_end: datetime, b_start: datetime, b_end: datetime) -> list[tuple[datetime, datetime]]:
    # returns intersection complement of [b_start,b_end) removed from [a_start,a_end)
    if not _overlaps(a_start, a_end, b_start, b_end):
        return [(a_start, a_end)]

    parts: list[tuple[datetime, datetime]] = []
    if a_start < b_start:
        parts.append((a_start, min(a_end, b_start)))
    if b_end < a_end:
        parts.append((max(a_start, b_end), a_end))
    return parts


def _merge_intervals(intervals: list[tuple[datetime, datetime]]) -> list[tuple[datetime, datetime]]:
    if not intervals:
        return []
    intervals.sort(key=lambda x: x[0])
    out: list[tuple[datetime, datetime]] = []
    for s, e in intervals:
        if not out:
            out.append((s, e))
            continue
        ps, pe = out[-1]
        if s <= pe:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def _snap_up(dt: datetime, step_min: int) -> datetime:
    step = timedelta(minutes=step_min)
    epoch = datetime(1970, 1, 1, tzinfo=dt.tzinfo)
    delta = dt - epoch
    step_s = step.total_seconds()
    total = int(delta.total_seconds() // step_s)
    snapped = epoch + total * step
    if snapped < dt:
        snapped += step
    return snapped


def _snap_down(dt: datetime, step_min: int) -> datetime:
    step = timedelta(minutes=step_min)
    epoch = datetime(1970, 1, 1, tzinfo=dt.tzinfo)
    delta = dt - epoch
    step_s = step.total_seconds()
    total = int(delta.total_seconds() // step_s)
    return epoch + total * step


def _snap_free_intervals(free: list[tuple[datetime, datetime]], slot_size_min: int) -> list[tuple[datetime, datetime]]:
    if slot_size_min <= 0:
        return free
    snapped: list[tuple[datetime, datetime]] = []
    for s, e in free:
        s2 = _snap_up(s, slot_size_min)
        e2 = _snap_down(e, slot_size_min)
        if e2 > s2:
            snapped.append((s2, e2))
    return _merge_intervals(snapped)


def _subtract_intervals(
    base: list[tuple[datetime, datetime]],
    subtract: list[tuple[datetime, datetime]],
) -> list[tuple[datetime, datetime]]:
    out = base[:]
    for s2, e2 in subtract:
        new_out: list[tuple[datetime, datetime]] = []
        for s1, e1 in out:
            if _overlaps(s1, e1, s2, e2):
                new_out.extend(_clip(s1, e1, s2, e2))
            else:
                new_out.append((s1, e1))
        out = _merge_intervals(new_out)
        if not out:
            break
    return out

def _is_aligned_to_slot(dt: datetime, slot_size_min: int) -> bool:
    if slot_size_min <= 0:
        return True
    step = timedelta(minutes=slot_size_min)
    epoch = datetime(1970, 1, 1, tzinfo=dt.tzinfo)
    delta = dt - epoch
    step_s = step.total_seconds()
    # allow small floating error by rounding via integers of seconds
    total = delta.total_seconds()
    return int(total) % int(step_s) == 0


# =========================
# Availability expansion
# =========================
def _weekday_in_inclusive_range(weekday_int: int, from_int: int, to_int: int) -> bool:
    """
    Inclusive weekday range on a 0..6 cycle.
    Examples:
      from=5 (Sat) to=1 (Tue) includes: Sat(5), Sun(6), Mon(0), Tue(1)
    """
    if from_int <= to_int:
        return from_int <= weekday_int <= to_int
    # wrap-around
    return weekday_int >= from_int or weekday_int <= to_int


def _expand_availability_to_free_intervals(
    availability: list[dict[str, Any]],
    horizon_start: date,
    horizon_days: int,
    tz: ZoneInfo,
) -> list[tuple[datetime, datetime]]:
    """
    Expand availability (FREE windows) for each day in [horizon_start, horizon_start+horizon_days).
    - periodic windows interpret from_day_of_week/to_day_of_week as inclusive weekday range (wrap-around allowed)
    - periodic/static time windows support overnight by treating end <= start as next day
    """
    availability = availability or []
    free: list[tuple[datetime, datetime]] = []

    horizon_end_date = horizon_start + timedelta(days=horizon_days)
    d = horizon_start
    while d < horizon_end_date:
        day_windows: list[tuple[datetime, datetime]] = []
        weekday = d.weekday()  # Mon=0..Sun=6

        for entry in availability:
            if not isinstance(entry, dict):
                continue

            # periodic
            if "periodic" in entry:
                periodic = entry.get("periodic")
                if not isinstance(periodic, dict):
                    continue

                from_dow = periodic.get("from_day_of_week")
                to_dow = periodic.get("to_day_of_week", from_dow)

                from_time = periodic.get("from_time")
                to_time = periodic.get("to_time")

                if from_dow is None or to_dow is None or from_time is None or to_time is None:
                    continue

                from_int = _dow_to_int(str(from_dow))
                to_int = _dow_to_int(str(to_dow))

                if not _weekday_in_inclusive_range(weekday_int=weekday, from_int=from_int, to_int=to_int):
                    continue

                st = _parse_hhmm(str(from_time))
                et = _parse_hhmm(str(to_time))
                start_dt = datetime.combine(d, st).replace(tzinfo=tz)
                end_dt = datetime.combine(d, et).replace(tzinfo=tz)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)

                day_windows.append((start_dt, end_dt))

            # static
            if "static" in entry:
                static = entry.get("static")
                if not isinstance(static, dict):
                    continue

                from_date = static.get("from_date")
                to_date = static.get("to_date")
                from_time = static.get("from_time")
                to_time = static.get("to_time")

                if from_date is None or to_date is None or from_time is None or to_time is None:
                    continue

                fd = date.fromisoformat(str(from_date))
                td = date.fromisoformat(str(to_date))
                if not (fd <= d <= td):
                    continue

                st = _parse_hhmm(str(from_time))
                et = _parse_hhmm(str(to_time))
                start_dt = datetime.combine(d, st).replace(tzinfo=tz)
                end_dt = datetime.combine(d, et).replace(tzinfo=tz)
                if end_dt <= start_dt:
                    end_dt += timedelta(days=1)

                day_windows.append((start_dt, end_dt))

        free.extend(day_windows)
        d += timedelta(days=1)

    return _merge_intervals(free)

# =========================
# iCalendar helpers
# =========================
def _ensure_ics_suffix(file_name: str) -> str:
    file_name = (file_name or "").strip()
    if not file_name:
        return "calendar.ics"
    p = Path(file_name)
    if p.suffix.lower() != ".ics":
        return f"{p.name}.ics"
    return p.name


def _get_component_interval(comp: Any, tz: ZoneInfo) -> tuple[datetime, datetime]:
    dtstart = comp.get("dtstart").dt
    dtend = comp.get("dtend").dt

    # dtstart/dtend might be date or datetime depending on how they were written.
    if isinstance(dtstart, date) and not isinstance(dtstart, datetime):
        dtstart = datetime(dtstart.year, dtstart.month, dtstart.day, tzinfo=tz)
    elif isinstance(dtstart, datetime):
        if dtstart.tzinfo is None:
            dtstart = dtstart.replace(tzinfo=tz)

    if isinstance(dtend, date) and not isinstance(dtend, datetime):
        dtend = datetime(dtend.year, dtend.month, dtend.day, tzinfo=tz)
    elif isinstance(dtend, datetime):
        if dtend.tzinfo is None:
            dtend = dtend.replace(tzinfo=tz)

    return dtstart, dtend


def _component_properties_as_jsonable(comp: Any) -> dict[str, Any]:
    props: dict[str, Any] = {}
    try:
        # comp.items() returns (key, value)
        for k, v in comp.items():
            ks = str(k)
            # icalendar values may be special; stringify for safety
            try:
                props[ks] = str(v)
            except Exception:
                props[ks] = repr(v)
    except Exception:
        pass
    return props


def _load_calendar(cal_path: Path) -> Calendar:
    return Calendar.from_ical(cal_path.read_bytes())


def _write_calendar(cal_path: Path, cal: Calendar) -> None:
    cal_path.parent.mkdir(parents=True, exist_ok=True)
    cal_path.write_bytes(cal.to_ical())


def _add_private_default_blocks(
    cal: Calendar,
    *,
    tz: ZoneInfo,
    horizon_days: int,
    start_hhmm: str,
    end_hhmm: str,
) -> None:
    sh = _parse_hhmm(start_hhmm)
    eh = _parse_hhmm(end_hhmm)

    today = datetime.now(tz=tz).date()
    for i in range(horizon_days):
        d = today + timedelta(days=i)
        start_dt = datetime.combine(d, sh).replace(tzinfo=tz)
        end_dt = datetime.combine(d, eh).replace(tzinfo=tz)
        if end_dt <= start_dt:
            end_dt += timedelta(days=1)

        ev = Event()
        ev.add("uid", f"private-{d.isoformat()}@default")
        ev.add("dtstamp", datetime.now(tz=tz))
        ev.add("dtstart", start_dt)
        ev.add("dtend", end_dt)
        ev.add("summary", "Private time")
        ev.add("class", "PRIVATE")  # marks private blocks
        cal.add_component(ev)


# =========================
# Actions
# =========================
def _action_create_calendar(params: dict[str, Any], action_obj: dict[str, Any]) -> dict[str, Any]:
    calendar_dir = params.get("calendar_dir")
    if not calendar_dir:
        return {"ok": False, "status": "error", "error": "calendar_dir param is required"}

    file_name = _ensure_ics_suffix(action_obj.get("file_name", "calendar.ics"))
    availability = action_obj.get("availability")  # optional; accepted but not stored
    if availability is not None and not isinstance(availability, list):
        return {
            "ok": False,
            "status": "error",
            "error": "availability (when provided to create_calendar) must be a list"
        }

    tz_name = params.get("timezone") or "UTC"
    tz = ZoneInfo(str(tz_name))

    horizon_days = int(params.get("horizon_days") or 30)

    cal_dir = Path(str(calendar_dir)).expanduser().resolve()
    out_path = cal_dir / file_name

    # Create empty calendar with default private blocks.
    cal = Calendar()
    cal.add("prodid", "-//CalendarICSUnit//EN")
    cal.add("version", "2.0")
    cal.add("calscale", "GREGORIAN")

    # Default private time 00:00-08:00 for next horizon_days.
    _add_private_default_blocks(
        cal,
        tz=tz,
        horizon_days=horizon_days,
        start_hhmm=str(params.get("default_private_start") or "00:00"),
        end_hhmm=str(params.get("default_private_end") or "08:00"),
    )

    # availability isn't stored as VEVENT here; it's an input to check_availability.
    # If you want it stored, we can add VFREEBUSY/VTODO representations.

    _write_calendar(out_path, cal)
    return {"ok": True, "path": str(out_path), "status": "created"}


def _parse_from_to_interval(from_d: dict[str, Any], to_d: dict[str, Any], tz: ZoneInfo) -> tuple[datetime, datetime]:
    def parse_one(d: dict[str, Any]) -> datetime:
        if not isinstance(d, dict):
            raise ValueError("from/to must be objects")
        dd = d.get("date")
        tt = d.get("time")
        if not dd or not tt:
            raise ValueError("from/to must include 'date' and 'time'")
        dt = datetime.fromisoformat(f"{dd}T{tt}")
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=tz)
        return dt

    start = parse_one(from_d)
    end = parse_one(to_d)
    return start, end


def _action_check_availability(params: dict[str, Any], action_obj: dict[str, Any]) -> dict[str, Any]:
    calendar_dir = params.get("calendar_dir")
    if not calendar_dir:
        return {"ok": False, "status": "error", "error": "calendar_dir param is required"}

    cal_file_name = action_obj.get("cal_file_name")
    if not cal_file_name:
        return {"ok": False, "status": "error", "error": "cal_file_name is required"}

    period_d = int(action_obj.get("period_d") or 30)
    include_scheduled_events = bool(action_obj.get("include_scheduled_events") or False)

    slot_size_min = int(params.get("slot_size_min") or 30)

    tz = ZoneInfo(str(params.get("timezone") or "UTC"))

    cal_dir = Path(str(calendar_dir)).expanduser().resolve()
    cal_path = cal_dir / _ensure_ics_suffix(str(cal_file_name))
    if not cal_path.exists():
        return {"ok": False, "status": "error", "error": f"calendar not found: {cal_path}"}

    # availability comes from unit params (per your spec) OR can be provided in create-calendar.
    availability = params.get("availability") if params.get("availability") is not None else action_obj.get("availability", None)
    if availability is None:
        availability = []
    if not isinstance(availability, list):
        return {
            "ok": False,
            "status": "error",
            "error": "availability must be a list of availability entries",
        }

    cal = _load_calendar(cal_path)

    busy: list[tuple[datetime, datetime]] = []
    private: list[tuple[datetime, datetime]] = []
    scheduled_events: list[dict[str, Any]] = []

    for comp in cal.walk():
        if getattr(comp, "name", None) != "VEVENT":
            continue
        s, e = _get_component_interval(comp, tz)
        klass = (comp.get("class") or "").upper()

        if klass == "PRIVATE":
            private.append((s, e))
        else:
            busy.append((s, e))

        if include_scheduled_events:
            scheduled_events.append(
                {
                    "uid": str(comp.get("uid") or ""),
                    "summary": str(comp.get("summary") or ""),
                    "class": klass,
                    "dtstart": s.isoformat(),
                    "dtend": e.isoformat(),
                    "properties": _component_properties_as_jsonable(comp),
                }
            )

    horizon_start = datetime.now(tz=tz).date()
    free_windows = _expand_availability_to_free_intervals(
        availability=availability,
        horizon_start=horizon_start,
        horizon_days=period_d,
        tz=tz,
    )

    # Everything not inside availability is implicitly unavailable (busy).
    free1 = _subtract_intervals(free_windows, busy)
    free2 = _subtract_intervals(free1, private)
    free2 = _snap_free_intervals(free2, slot_size_min)

    result: dict[str, Any] = {
        "ok": True,
        "slot_size_min": slot_size_min,
        "free_slots": [{"from": s.isoformat(), "to": e.isoformat()} for s, e in free2],
    }
    if include_scheduled_events:
        result["scheduled_events"] = scheduled_events
    return result


def _action_reserve(params: dict[str, Any], action_obj: dict[str, Any]) -> dict[str, Any]:
    calendar_dir = params.get("calendar_dir")
    if not calendar_dir:
        return {"ok": False, "status": "error", "error": "calendar_dir param is required"}

    cal_file_name = action_obj.get("cal_file_name")
    if not cal_file_name:
        return {"ok": False, "status": "error", "error": "cal_file_name is required"}

    from_d = action_obj.get("from")
    to_d = action_obj.get("to")
    event_name = action_obj.get("event_name") or "Reserved"
    properties = action_obj.get("properties")
    slot_size_min = int(params.get("slot_size_min") or 30)
    enforce_alignment = bool(params.get("reserve_enforce_slot_alignment") if "reserve_enforce_slot_alignment" in params else True)


    tz = ZoneInfo(str(params.get("timezone") or "UTC"))
    cal_dir = Path(str(calendar_dir)).expanduser().resolve()
    cal_path = cal_dir / _ensure_ics_suffix(str(cal_file_name))
    if not cal_path.exists():
        return {"ok": False, "status": "error", "error": f"calendar not found: {cal_path}"}

    if not isinstance(from_d, dict) or not isinstance(to_d, dict):
        return {"ok": False, "status": "error", "error": "reserve requires from/to objects"}

    start, end = _parse_from_to_interval(from_d, to_d, tz)
    if end <= start:
        return {"ok": False, "status": "error", "error": "invalid interval: to must be after from"}
    if enforce_alignment:
        if not _is_aligned_to_slot(start, slot_size_min) or not _is_aligned_to_slot(end, slot_size_min):
            return {
                "ok": False,
                "status": "error",
                "error": f"reserve interval must align to slot_size_min={slot_size_min} boundaries"
            }

    cal = _load_calendar(cal_path)

    private_intervals: list[tuple[datetime, datetime]] = []
    busy_intervals: list[tuple[datetime, datetime]] = []

    # Collect existing intervals
    for comp in cal.walk():
        if getattr(comp, "name", None) != "VEVENT":
            continue
        s, e = _get_component_interval(comp, tz)
        klass = (comp.get("class") or "").upper()
        if klass == "PRIVATE":
            private_intervals.append((s, e))
        else:
            busy_intervals.append((s, e))

    # Enforce private-time protection
    for ps, pe in private_intervals:
        if _overlaps(start, end, ps, pe):
            return {"ok": False, "status": "error", "error": "requested time overlaps private time"}

    # Enforce busy overlap (everything else is busy)
    for bs, be in busy_intervals:
        if _overlaps(start, end, bs, be):
            return {"ok": False, "status": "error", "error": "requested time overlaps existing busy event"}

    # Create VEVENT for reservation (busy by default; not private)
    uid = f"evt-{int(datetime.now(tz=tz).timestamp() * 1000)}@local"

    ev = Event()
    ev.add("uid", uid)
    ev.add("dtstamp", datetime.now(tz=tz))
    ev.add("dtstart", start)
    ev.add("dtend", end)
    ev.add("summary", str(event_name))
    # CLASS omitted => treated as busy (not private)

    if isinstance(properties, dict):
        # Add custom properties. Keep values stringified.
        # In production you should allowlist keys to avoid invalid iCalendar fields.
        for k, v in properties.items():
            ev.add(str(k), str(v))

    cal.add_component(ev)
    _write_calendar(cal_path, cal)

    # Use UID as event_id for cancellation.
    return {"ok": True, "status": "reserved", "calendar_path": str(cal_path), "event_id": uid}


def _action_cancel(params: dict[str, Any], action_obj: dict[str, Any]) -> dict[str, Any]:
    calendar_dir = params.get("calendar_dir")
    if not calendar_dir:
        return {"ok": False, "status": "error", "error": "calendar_dir param is required"}

    cal_file_name = action_obj.get("cal_file_name")
    if not cal_file_name:
        return {"ok": False, "status": "error", "error": "cal_file_name is required"}
    event_id = action_obj.get("event_id")
    if not event_id:
        return {"ok": False, "status": "error", "error": "event_id is required"}

    cal_dir = Path(str(calendar_dir)).expanduser().resolve()
    cal_path = cal_dir / _ensure_ics_suffix(str(cal_file_name))
    if not cal_path.exists():
        return {"ok": False, "status": "error", "error": f"calendar not found: {cal_path}"}

    cal = _load_calendar(cal_path)

    target_uid = str(event_id)
    removed = False

    # iCalendar components from icalendar don’t always support easy removal in-place.
    # Rebuild VCALENDAR by filtering VEVENTs.
    new_cal = Calendar()
    for k, v in cal.items():
        new_cal.add(k, v)
    for comp in cal.subcomponents:
        if getattr(comp, "name", None) == "VEVENT":
            uid = comp.get("uid")
            uid_s = str(uid) if uid is not None else ""
            if uid_s == target_uid:
                removed = True
                continue
        new_cal.add_component(comp)

    if removed:
        _write_calendar(cal_path, new_cal)

    return {"ok": removed, "status": "cancelled" if removed else "not_found", "calendar_path": str(cal_path)}


# =========================
# Unit step
# =========================
def _step_fn(params: dict[str, Any], inputs: dict[str, Any], state: dict[str, Any], dt: float):
    action_obj = inputs.get("input")
    if not isinstance(action_obj, dict):
        return ({"data": {"ok": False}, "error": "input must be an object"}, state)

    action = action_obj.get("action")
    if action != "calendar":
        return ({"data": {"ok": False}, "error": "input.action must be 'calendar'"}, state)

    method = action_obj.get("method")
    if not method:
        return ({"data": {"ok": False}, "error": "method is required"}, state)

    try:
        if method == "create_calendar":
            data = _action_create_calendar(params=params, action_obj=action_obj)
            return ({"data": data, "error": None if data.get("ok") else (data.get("error") or "error")}, state)

        if method == "get_all_calendars":
            calendar_dir = params.get("calendar_dir")
            if not calendar_dir:
                return ({"data": {"ok": False}, "error": "calendar_dir param is required"}, state)
            cal_dir = Path(str(calendar_dir)).expanduser().resolve()
            if not cal_dir.exists():
                return ({"data": {"ok": True, "calendars": []}, "error": None}, state)
            files = sorted([p.name for p in cal_dir.glob("*.ics") if p.is_file()])
            return ({"data": {"ok": True, "calendars": files}, "error": None}, state)

        if method == "check_availability":
            data = _action_check_availability(params=params, action_obj=action_obj)
            return ({"data": data, "error": None if data.get("ok") else (data.get("error") or "error")}, state)

        if method == "reserve":
            data = _action_reserve(params=params, action_obj=action_obj)
            return ({"data": data, "error": None if data.get("ok") else (data.get("error") or "error")}, state)

        if method == "cancel":
            data = _action_cancel(params=params, action_obj=action_obj)
            return ({"data": data, "error": None if data.get("ok") else (data.get("error") or "error")}, state)

        return ({"data": {"ok": False}, "error": f"unsupported method: {method}"}, state)
    except Exception as e:
        return ({"data": {"ok": False}, "error": str(e)}, state)

def register_calendar_unit() -> None:
    register_unit(
        UnitSpec(
            type_name="CalendarICS",
            input_ports=CAL_INPUT_PORTS,
            output_ports=CAL_OUTPUT_PORTS,
            step_fn=_step_fn,
            environment_tags=["time"],
            environment_tags_are_agnostic=False,
            description=(
                "Manage iCalendar (.ics) calendar with actions: create_calendar, get_all_calendars, "
                "check_availability (returns free slots; optional include_scheduled_events), reserve, cancel. "
                "Default private time is 00:00-08:00 daily (next horizon_days) stored as VEVENT CLASS:PRIVATE."
            ),
        )
    )
