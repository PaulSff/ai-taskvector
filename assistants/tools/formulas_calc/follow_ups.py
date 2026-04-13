"""formulas_calc tool: follow-up prompt fragments."""

FORMULAS_CALC_FOLLOW_UP_PREFIX = (
    "IMPORTANT: Excel formula calculation results are below (authoritative JSON). "
    "Quote the numeric values in your reply so the user can see them; cite cell keys exactly as shown.\n\n"
)

FORMULAS_CALC_FOLLOW_UP_SUFFIX = (
    "\n\nSummarize numeric results clearly for the user. Reply in {language} "
    "(session preference: {session_language})."
)
