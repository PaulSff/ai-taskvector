"""formulas_calc tool: follow-up prompt fragments."""

FORMULAS_CALC_FOLLOW_UP_PREFIX = (
    "IMPORTANT: Excel formula calculation results are below (authoritative JSON). "
    "Quote the numeric values in your reply so the user can see them; cite cell keys exactly as shown.\n\n"
)

FORMULAS_CALC_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize numeric results clearly for the user. Quote the computed values with their cell keys. Reply in {language} "
    "(session preference: {session_language})."
)

FORMULAS_CALC_FOLLOW_UP_USER_MESSAGE = (
    "Summarize the calculation result please: Initial task, Inputs, Outputs, Outcome."
    "Respond in {session_language}."
)
