"""Calendar tool prompt lines"""

TOOL_ACTION_PROMPT_LINE = ("""- Calendar actions:
        - get_all_calendars - Retuns a list of available calendars: { "action": "get_all_calendars" }
        - check_availability - Returns free slots: { "action": "check_availability", "cal_file_name": "calendar.ics", "period_d": 30, "include_scheduled_events": false/true, "availability": [ {"periodic": { "from_day_of_week": "mon", "to_day_of_week": "fri", "from_time": "09:00", "to_time": "17:00" } } ] } -  Set `include_scheduled_events: true` to include reserved events.
        - reserve - Reserves a slot: { "action": "reserve", "cal_file_name": "calendar.ics", "from": { "date": "2026-08-20", "time": "09:00" }, "to":   { "date": "2026-08-20", "time": "10:00" }, "event_name": "<your_event_or_meeting_name>"}
        - cancel - Cancel existing reservation: { "action": "cancel", "cal_file_name": "calendar.ics", event_id": "evt-1720000000000@local" }
        """
)
