"""TODO list manager prompt lines"""

TASK_PREFIX_REVIEW_SOURCE = "Review the source "
TASK_PREFIX_ADD_CODE_BLOCK = "Add the code block to "

TASK_REVIEW_IMPORTED_WORKFLOW = "Review the workflow"

TASK_ENSURE_UNITS_CONNECTED = "Verify the units connections and ports: {unit_ids}. Ensure the ports types compatibility (e.g. 'tables' -> 'tables') to pass the data in correct format."
TASK_CHECK_UNITS_PARAMS = "Search the units params description on the knowledge base, unless it is a custom function: {unit_ids}. Trace data keys all the way through the flow and adjust the units params to meet the specificaton."
TASK_ENSURE_DEBUG_FOR_RUN = (
    "Ensure to have a Debug unit in place to collect both output Data and Errors from units (typically at the tail of the workflow). "
    "Set a log file path in the Debug unit params to grep the logs from there. "
)
TASK_PREPARE_INITIAL_DATA_FOR_RUN = "Ensure the to have a Template unit with some input data in params for the workflow to test with. Test the workflow, put a comment summarizing the testing result on the graph."

TASK_PREFIX_REPLY_TO_INCOMING_MESSAGE = "Respond to the incoming message: "
