"""Post-apply review strings when a graph comment is added (any assistant role using ``add_comment`` edits)."""

ADD_COMMENT_REVIEW_SYSTEM = (
    "IMPORTANT: Your comment was added. You must review the comment. Respond in {session_language}."
)
ADD_COMMENT_REVIEW_USER_MESSAGE = "Review your comment and continue. Respond in {session_language}."
