"""air_shopping_rq tool: follow-up prompt fragments."""

AIR_SHOPPING_RQ_FOLLOW_UP_PREFIX = (
    "IMPORTANT: You requested a low-fare flight calendar on the prevous turn (air_shopping_rq). You must check the response:\n\n"
)

AIR_SHOPPING_RQ_FOLLOW_UP_SUFFIX = (
    "\n\n Summarize the response above. In case of any error taking place, correct yourself, then give it another try. "
    "Respond in {session_language}."
)
