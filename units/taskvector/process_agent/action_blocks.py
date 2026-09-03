"""
Parse LLM output into generic action blocks (any dict with an "action" key).

**Content form:** The input is a single string — the raw LLM response. In the agent
workflow this comes from the **LLMAgent** unit (output port `action` → ProcessAgent input
port `action`). The string may be plain text, markdown, and/or contain fenced ```json
blocks or inline { ... } JSON; this module extracts and parses those blocks.

Used by the ProcessAgent unit. Does not reference GraphEditAction or any domain-specific type;
downstream units (e.g. ApplyEdits) filter by their own action set.
Self-contained: JSON block extraction is in this module (no dependency on agents).

Summary Table

Strategy	Trigger    Main Goal   Key Strength
Fenced  	```json	    Find structured blocks  	Handles nested backticks correctly
Inline  	{ ... }	    Find "naked" JSON	Recovers data when LLM forgets fences
Cleaning	Any block	Fix syntax errors	Allows comments and trailing commas
Filtering	Parsed Obj	Remove noise	Ensures only "Actions" are executed
"""

from __future__ import annotations

from typing import cast

from pydantic import ValidationError

from agents.tools.types import ParsedActions, ParserOutput
from core.graph import GraphEdit
from core.schemas.primitives import (
    Data,
    JsonObject,
    JsonValue,
    is_json_object,
)

from .parser import parse_json_blocks

_SIMPLE_OBJECT_ACTIONS: dict[str, str] = {
    "report": "report",
    "formulas_calc": "formulas_calc",
    "delegate_request": "delegate_request",
    "calendar": "calendar",
    "clone_role": "clone_role",
    "list_dir": "list_dir",
    "no_edit": "no_edit",
}


def parse_action_blocks(content: str) -> ParserOutput:
    """
    Parse LLM content into normalized ParsedActions.
    """
    parsed = parse_json_blocks(content)

    if isinstance(parsed, str):
        return ParserOutput(error=parsed)

    return _parsed_blocks_to_action_blocks(parsed)


def _parsed_blocks_to_action_blocks(
    parsed_blocks: list[JsonValue],
) -> ParserOutput:
    """
    Convert parsed JSON blocks into a normalized ParsedActions instance.

    ParsedActions is used as the accumulator so the parser does not maintain
    a second, duplicated set of local declarations.
    """
    actions = ParsedActions()
    raw_edits: list[JsonObject] = []

    def collect_one(obj: JsonObject) -> None:
        action = obj.get("action")

        if not isinstance(action, str):
            nested_edits = obj.get("edits")

            if isinstance(nested_edits, list):
                for item in nested_edits:
                    if is_json_object(item):
                        collect_one(item)
            return

        if action == "read_file":
            path = obj.get("path")

            if isinstance(path, str) and path.strip():
                actions.read_file.append(path.strip())

            return

        if action == "read_code_block":
            block_id = obj.get("id")

            if isinstance(block_id, str) and block_id.strip():
                actions.read_code_block_ids.append(block_id.strip())

            elif isinstance(block_id, list):
                actions.read_code_block_ids.extend(
                    item.strip()
                    for item in block_id
                    if isinstance(item, str) and item.strip()
                )

            return

        if action == "read_current_workflow":
            actions.read_current_workflow = True
            return

        if action == "web_search":
            _parse_web_search(obj, actions)
            return

        if action == "browse":
            url = obj.get("url") or obj.get("URL")

            if isinstance(url, str) and url.strip():
                actions.browse_url = url.strip()

            return

        if action == "github":
            payload = obj.get("payload")

            if isinstance(payload, dict) and payload.get("action"):
                actions.github = cast(Data, payload)

            return

        if action == "run_workflow":
            actions.run_workflow = {
                "action": "run_workflow",
                "path": (
                    obj.get("path")
                    if isinstance(obj.get("path"), str)
                    else None
                ),
            }

            return

        if action == "grep":
            actions.grep = _parse_grep(obj)
            return

        if action == "send_message":
            message = _parse_send_message(obj)

            if message is not None:
                actions.send_message.append(message)

            return

        if action == "get_unread":
            unread_request = _parse_get_unread(obj)

            if unread_request is not None:
                actions.get_unread.append(unread_request)

            return

        if action == "new_file":
            actions.new_file = _parse_new_file(obj)
            return

        if action == "edit_file":
            actions.edit_file = _parse_edit_file(obj)
            return

        if action == "rename":
            actions.rename = _parse_rename(obj)
            return

        if action == "delete":
            actions.delete = _parse_path_action(obj, "delete")
            return

        if action == "make_dir":
            actions.make_dir = _parse_path_action(obj, "make_dir")
            return

        if action == "search":
            query = obj.get("query")

            if isinstance(query, str) and query.strip():
                actions.rag_search = dict(obj)
                raw_edits.append(obj)

            return

        if action in _SIMPLE_OBJECT_ACTIONS:
            field_name = _SIMPLE_OBJECT_ACTIONS[action]
            setattr(actions, field_name, dict(obj))
            return

        # Preserve unknown action-shaped objects for GraphEdit validation.
        raw_edits.append(obj)

    for parsed in parsed_blocks:
        if isinstance(parsed, list):
            for item in parsed:
                if is_json_object(item):
                    collect_one(item)

        elif is_json_object(parsed):
            collect_one(parsed)

    for raw_edit in raw_edits:
        try:
            actions.edits.append(GraphEdit.model_validate(raw_edit))
        except ValidationError:
            continue

    actions.read_file = list(dict.fromkeys(actions.read_file))
    actions.read_code_block_ids = list(dict.fromkeys(actions.read_code_block_ids))

    return ParserOutput(actions=actions)


def _parse_web_search(
    obj: JsonObject,
    actions: ParsedActions,
) -> None:
    query = obj.get("query")

    if isinstance(query, str) and query.strip():
        actions.web_search = query.strip()

    max_results = obj.get("max_results")

    if isinstance(max_results, bool):
        return

    if isinstance(max_results, int):
        if max_results >= 1:
            actions.web_search_max_results = min(20, max_results)

        return

    if isinstance(max_results, float):
        if max_results.is_integer() and max_results >= 1:
            actions.web_search_max_results = min(20, int(max_results))

        return

    if isinstance(max_results, str):
        try:
            parsed_max_results = int(max_results.strip())
        except ValueError:
            return

        if parsed_max_results >= 1:
            actions.web_search_max_results = min(20, parsed_max_results)


def _parse_grep(obj: JsonObject) -> Data | None:
    pattern = obj.get("pattern") or obj.get("command") or obj.get("regex")
    source = obj.get("source")

    if not isinstance(pattern, str) or not pattern.strip():
        return None

    return {
        "action": "grep",
        "grep": {
            "pattern": pattern.strip(),
            "source": source if isinstance(source, str) else None,
        },
    }


def _parse_send_message(obj: JsonObject) -> Data | None:
    message: Data = {"action": "send_message"}

    messenger = obj.get("messenger")
    chat_id = obj.get("chat_id")
    text = obj.get("message")

    if isinstance(messenger, str) and messenger.strip():
        message["messenger"] = messenger.strip()

    if isinstance(chat_id, (str, int)) and str(chat_id).strip():
        message["chat_id"] = str(chat_id).strip()

    if isinstance(text, str) and text.strip():
        message["message"] = text

    return message


def _parse_get_unread(obj: JsonObject) -> Data | None:
    messenger = obj.get("messenger")

    if isinstance(messenger, str):
        messenger = messenger.strip()

    if not messenger:
        return None

    return {
        "action": "get_unread",
        "messenger": messenger,
    }


def _parse_new_file(obj: JsonObject) -> Data | None:
    output_dir = obj.get("output_dir")
    raw_file = obj.get("file")

    if not isinstance(output_dir, str) or not output_dir.strip():
        return None

    if not isinstance(raw_file, dict):
        return None

    file_name = raw_file.get("file_name")
    content = raw_file.get("content")
    output_format = raw_file.get("output_format")

    if not isinstance(file_name, str) or not file_name.strip():
        return None

    if not isinstance(content, str):
        return None

    file_data: Data = {
        "file_name": file_name.strip(),
        "content": content,
    }

    if isinstance(output_format, str) and output_format.strip():
        file_data["output_format"] = output_format.strip()

    return {
        "action": "new_file",
        "output_dir": output_dir.strip(),
        "file": file_data,
    }


def _parse_edit_file(obj: JsonObject) -> Data | None:
    output_dir = obj.get("output_dir")
    raw_file = obj.get("file")

    if not isinstance(output_dir, str) or not output_dir.strip():
        return None

    if not isinstance(raw_file, dict):
        return None

    file_name = raw_file.get("file_name")

    if not isinstance(file_name, str) or not file_name.strip():
        return None

    replacements = {
        key: value
        for key, value in raw_file.items()
        if key.startswith("replacement_")
    }

    if not replacements:
        return None

    parsed_replacements: dict[str, Data] = {}

    for key, raw_value in replacements.items():
        if not isinstance(raw_value, dict):
            return None

        find_text = raw_value.get("find")
        replace_with = raw_value.get("replace_with")
        line_num_ref = raw_value.get("line_num_ref")

        if not isinstance(find_text, str) or not find_text:
            return None

        if not isinstance(replace_with, str):
            return None

        normalized_line_num_ref = _normalize_line_number(line_num_ref)

        if normalized_line_num_ref is None:
            return None

        parsed_replacements[key] = {
            "find": find_text,
            "replace_with": replace_with,
            "line_num_ref": normalized_line_num_ref,
        }

    return {
        "action": "edit_file",
        "output_dir": output_dir.strip(),
        "file": {
            "file_name": file_name.strip(),
            **parsed_replacements,
        },
    }


def _normalize_line_number(value: object) -> str | None:
    if isinstance(value, bool):
        return None

    if isinstance(value, int):
        return str(value)

    if isinstance(value, float) and value.is_integer():
        return str(int(value))

    if isinstance(value, str) and value.strip():
        return value.strip()

    return None


def _parse_rename(obj: JsonObject) -> Data | None:
    path = obj.get("path")
    new_name = obj.get("new_name")

    if not isinstance(path, str) or not path.strip():
        return None

    if not isinstance(new_name, str) or not new_name.strip():
        return None

    return {
        "action": "rename",
        "path": path.strip(),
        "new_name": new_name.strip(),
    }


def _parse_path_action(
    obj: JsonObject,
    action: str,
) -> Data | None:
    path = obj.get("path")

    if not isinstance(path, str) or not path.strip():
        return None

    return {
        "action": action,
        "path": path.strip(),
    }


def parse_workflow_edits(content: str) -> ParserOutput:
    """Alias for parse_action_blocks for backward compatibility."""
    return parse_action_blocks(content)
