"""run_workflow skill: follow-up prompt fragments."""

from assistants.skills.follow_up_common import FOLLOW_UP_RESPONSE_SESSION_SUFFIX

RUN_WORKFLOW_FOLLOW_UP_PREFIX = "IMPORTANT: You requested to run the workflow. You must check the run result.\n\n"
RUN_WORKFLOW_FOLLOW_UP_SUFFIX = FOLLOW_UP_RESPONSE_SESSION_SUFFIX
