"""Cross-role assistants chat strings (post-apply and similar), not tied to one role module."""

# Default post-apply round: first ``run_post_apply_follow_up_rounds`` message when apply was not
# import-only / comment-only / todo-only (Workflow Designer + Analyst share ``parser_follow_up.chain``).
DEFAULT_POST_APPLY_FOLLOW_UP_INJECT = (
    "IMPORTANT: Your edits were applied. You must review the current graph summary and recent changes, fix the issues if there are any. "
    "Check the TODO list, pick up the tasks remaining, mark all finished tasks as completed. If the job is finished, share a short summary with the user. Otherwise, continue with your edits. "
    "Respond in {session_language}."
)
DEFAULT_POST_APPLY_FOLLOW_UP_USER_MESSAGE = (
    "Please, review the changes. Share a brief summary, if the job is finished. Continue with your edits, otherwise. Respond in {session_language}. "
)
