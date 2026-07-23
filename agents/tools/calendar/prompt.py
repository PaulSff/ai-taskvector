"""Calendar tool prompt lines"""

TOOL_ACTION_PROMPT_LINE = ("""- Calendar actions:
        - get_all_calendars - Retuns a list of available calendars: { "action": "calendar", "method": "get_all_calendars" }
        - check_availability: "action": "calendar", "method": "check_availability", "cal_file_name": "your_calendar.ics", "period_d": 30, "include_scheduled_events": false/true, "availability": [ {"periodic": { "from_day_of_week": "mon", "to_day_of_week": "fri", "from_time": "09:00", "to_time": "17:00" } } ] } -  Set `include_scheduled_events: true` to include reserved events.
        - reserve: { "action": "calendar", "method": "reserve", "cal_file_name": "calendar.ics", "from": { "date": "....-..-..", "time": "..:.." }, "to": { "date": "....-..-.", "time": "..:.." }, "event_name": "..." }
        - cancel - Cancel an existing reservation: { "action": "calendar", "method": "cancel", "cal_file_name": "calendar.ics", event_id": "...@..." }"""
)
