"""air_shopping_rq tool: follow-up prompt fragments."""

AIR_SHOPPING_RQ_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested the low-fare flight calendar. You must check the response from GDS:\n\n"
)

AIR_SHOPPING_RQ_FOLLOW_UP_SUFFIX = (
    "\n\n Summarize the flight offers above into an easy-to-compare kind of table for the user."
    "In case of any error taking place, correct yourself, then give it another try. "
    "Respond in {session_language}."
)
