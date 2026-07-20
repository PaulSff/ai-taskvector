"""calendar tool: follow-up prompt fragments."""

CALENDAR_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested the Callendar action. You must check the results below and share it with the user.\n\n"
)

CALENDAR_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the calendar output for the user. Quote and interpret the output keys: `free_slots: [ { from:...; to...} ]` - free slots available to reserve (availability); `slot_size_min` - min time slot to reserve in minutes; `scheduled_events` - events currently reserved (only present if availability was requested requested with `include_scheduled_events: true`); `class` PRIVATE - cannot be cancelled (private time); `status` reserved/cancelled; ok: true - request succeeded, etc. "
    "Respond in {session_language}. Append JSON block with `no_edit` action at the tail."
)

CALENDAR_FOLLOW_UP_USER_MESSAGE = (
    "Please share the available options/ to consider (or any results if already reserved): availability/reservation status, etc. Append a ```json ...``` block with no_edit action at the tail!"
)
