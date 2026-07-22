"""calendar tool: follow-up prompt fragments."""

CALENDAR_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested the Callendar action. You must check the results below and share it with the user. Avoid greetings, you already said hello to the user last turn.\n\n"
)

CALENDAR_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize the calendar output for the user. Quote and interpret what you have on schedule. Note: `free_slots` - available on schedule; `slot_size_min` - minimum time slot to reserve; `scheduled_events` - events currently reserved (only present if availability was requested requested with `include_scheduled_events: true`); `class` PRIVATE - cannot be cancelled (private time); `status` reserved/cancelled; "
    "Respond in {session_language}."
)

CALENDAR_FOLLOW_UP_USER_MESSAGE = (
    "Please, check the outcome and share the status on scheduling."
)
