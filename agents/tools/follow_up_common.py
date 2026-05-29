"""Lines shared across tool follow-up modules (empty-tool UX, session-language suffix)."""

TOOL_EMPTY_RESULT_LINE = "(Nothing found: no data was returned for this request.)"

# Appended to injected tool context so the model answers in the session language.
FOLLOW_UP_RESPONSE_SESSION_SUFFIX = "\n\nRespond in {session_language}."

# User message when a follow-up tool returned nothing usable (orchestrator; Workflow Designer path).
TOOL_EMPTY_USER_MESSAGE = (
    "Nothing usable was returned for your last request. Check the status and continue with your edits, if suitable. Otherwise, share the summary. "
    "Respond in {session_language}."
)
