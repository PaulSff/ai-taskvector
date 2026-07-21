"""Cross-role agents chat strings (post-apply and similar), not tied to one role module."""

# Default post-apply round: first ``run_post_apply_follow_up_rounds`` message when apply was not
# import-only / comment-only / todo-only (Workflow Designer + Analyst share ``parser_follow_up.chain``).
DEFAULT_POST_APPLY_FOLLOW_UP_INJECT = (
    "IMPORTANT: Your edits were applied. You must review the the current graph summary, recent changes, follow up context, fix the issues if there are any. "
    "Check the TODO list, pick up the tasks remaining, mark all finished tasks as completed. If the job is finished, share a short summary with the user. Otherwise, continue with your edits. "
    "Respond in {session_language}."
)
DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE = "Please, review the changes, follow up context for any results. Share a brief summary, if the job is finished or needs clarifications. Continue with your edits, otherwise. Respond in {session_language}. "

# Constant user message sent to the workflow on follow-up runs (file/RAG/web/browse/code_block); context is in follow_up_context.
DEFAULT_FOLLOW_UP_USER_MESSAGE = "Check out the result. Share the brief summary. Respond in {session_language}."
