"""Post-apply chat injects after a successful ``import_workflow`` graph edit (not parser-output follow-up chain)."""

# Injected as ``follow_up_context`` / system-side copy for the first post-apply assistant round when
# ``PostApplyFlags.had_import_workflow`` is true (see ``gui.chat.parser_follow_up.chain``).
IMPORT_POST_APPLY_INJECT = (
    "IMPORTANT: The workflow has been imported successfully. The graph has been replaced. "
    "You must explain how the imported workflow works, then emit mark_completed on \"Review the workflow\" task. "
    "Respond in {session_language}."
)
IMPORT_POST_APPLY_USER_MESSAGE = (
    "Review the workflow just imported. Describe how it works and how to use it. Respond in {session_language}."
)
