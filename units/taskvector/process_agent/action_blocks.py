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


def parse_action_blocks(content: str) -> ParserOutput:
    """
    Parse LLM content into a generic list of action blocks (any dict with an "action" key).
    """
    parsed = parse_json_blocks(content)

    if isinstance(parsed, str):
        return ParserOutput(error=parsed)

    return _parsed_blocks_to_action_blocks(parsed)


def _parsed_blocks_to_action_blocks(
    parsed_blocks: list[JsonValue],
) -> ParserOutput:
    """Convert parsed JSON blocks to flat list of action dicts; extract side-channel actions into separate keys."""
    edits: list[JsonObject] = []
    read_file_paths: list[str] = []
    read_code_block_ids: list[str] = []

    web_search_query: str | None = None
    web_search_max_results: int | None = None
    browse_url: str | None = None

    github_obj: Data | None = None
    report_obj: Data | None = None
    run_workflow_obj: Data | None = None
    grep_obj: Data | None = None
    formulas_calc_obj: Data | None = None
    delegate_request_obj: Data | None = None

    read_current_workflow_requested = False

    send_messages: list[Data] = []
    get_unreads: list[Data] = []

    calendar_obj: Data | None = None
    clone_role_obj: Data | None = None
    rag_search_obj: Data | None = None
    list_dir_obj: Data | None = None
    new_file_obj: Data | None = None
    edit_file_obj: Data | None = None
    rename_obj: Data | None = None
    delete_obj: Data | None = None
    make_dir_obj: Data | None = None
    no_edit_obj: Data | None = None

    def collect_one(obj: JsonObject) -> None:
        grey = "\033[38;5;245m"
        reset = "\033[0m"
        print(f"{grey}[action_blocks]collect_one obj: {obj}{reset}", flush=True)

        nonlocal no_edit_obj
        nonlocal \
            read_code_block_ids
        nonlocal web_search_query, web_search_max_results, browse_url, github_obj
        nonlocal \
            report_obj, \
            run_workflow_obj, \
            grep_obj, \
            formulas_calc_obj, \
            delegate_request_obj, \
            read_current_workflow_requested, \
            calendar_obj, \
            clone_role_obj, \
            rag_search_obj, \
            list_dir_obj, \
            new_file_obj, \
            edit_file_obj, \
            rename_obj, \
            delete_obj, \
            make_dir_obj
        if obj.get("action") == "read_file":
            path = obj.get("path")
            if isinstance(path, str) and path.strip():
                read_file_paths.append(path.strip())
            return
        if obj.get("action") == "search":
            q = obj.get("query")
            if not (isinstance(q, str) and q.strip()):
                return
            rag_search_obj = dict(obj)
            edits.append(obj)
            return
        if obj.get("action") == "read_code_block":
            bid = obj.get("id")
            if isinstance(bid, str) and bid.strip():
                read_code_block_ids.append(bid.strip())
            elif isinstance(bid, list):
                for x in bid:
                    if isinstance(x, str) and x.strip():
                        read_code_block_ids.append(x.strip())
            return
        if obj.get("action") == "read_current_workflow":
            read_current_workflow_requested = True
            return
        mr = obj.get("max_results")

        if isinstance(mr, bool):
            pass  # Reject booleans explicitly
        elif isinstance(mr, int):
            if mr >= 1:
                web_search_max_results = min(20, mr)
        elif isinstance(mr, float):
            if mr.is_integer() and mr >= 1:
                web_search_max_results = min(20, int(mr))
        elif isinstance(mr, str):
            try:
                n = int(mr.strip())
            except ValueError:
                pass
            else:
                if n >= 1:
                    web_search_max_results = min(20, n)

            return
        if obj.get("action") == "browse":
            u = obj.get("url") or obj.get("URL")
            if isinstance(u, str) and u.strip():
                browse_url = u.strip()
            return
        if obj.get("action") == "github":
            payload = obj.get("payload")
            if isinstance(payload, dict) and payload.get("action"):
                github_obj = cast(Data, payload)
            return
        if obj.get("action") == "report":
            report_obj = cast(Data, obj)
            return
        if obj.get("action") == "list_dir":
            list_dir_obj = cast(Data, dict(obj))
            return
        if obj.get("action") == "run_workflow":
            run_workflow_obj = {
                "action": "run_workflow",
                "path": obj.get("path") if isinstance(obj.get("path"), str) else None,
            }
            return
        if obj.get("action") == "grep":
            pat = obj.get("pattern") or obj.get("command") or obj.get("regex")
            src = obj.get("source")
            if isinstance(pat, str) and pat.strip():
                grep_obj = {
                    "action": "grep",
                    "grep": {
                    "pattern": pat.strip(),
                    "source": src if isinstance(src, str) else None,
                    }
                }
            return
        if obj.get("action") == "formulas_calc":
            formulas_calc_obj = dict(obj)
            return
        if obj.get("action") == "delegate_request":
            delegate_request_obj = dict(obj)
            return
        if obj.get("action") == "send_message":
            m: Data = {"action": "send_message"}
            messenger = obj.get("messenger")
            chat_id = obj.get("chat_id")
            message = obj.get("message")
            if isinstance(messenger, str) and messenger.strip():
                m["messenger"] = messenger.strip()
            if isinstance(chat_id, (str, int)) and str(chat_id).strip():
                m["chat_id"] = str(chat_id).strip()
            if isinstance(message, str) and message.strip():
                m["message"] = message
            send_messages.append(m)
            return
        if obj.get("action") == "get_unread":
            messenger = obj.get("messenger")
            if isinstance(messenger, str):
                messenger = messenger.strip()
            if messenger:
                get_unreads.append(
                    {
                        "action": "get_unread",
                        "messenger": messenger,
                    }
                )
            return
        if obj.get("action") == "calendar":
            calendar_obj = dict(obj)
            return
        if obj.get("action") == "clone_role":
            clone_role_obj = dict(obj)
            return
        if obj.get("action") == "new_file":
            output_dir = obj.get("output_dir")
            file_obj = obj.get("file")
            if not (isinstance(output_dir, str) and output_dir.strip()):
                return
            if not isinstance(file_obj, dict):
                return
            output_format = file_obj.get("output_format")
            file_name = file_obj.get("file_name")
            content = file_obj.get("content")
            if not (isinstance(file_name, str) and file_name.strip()):
                return
            if not (isinstance(content, str)):
                return
            new_file_obj = {
                "action": "new_file",
                "output_dir": output_dir.strip(),
                "file": {
                    **({ "output_format": output_format.strip() } if isinstance(output_format, str) and output_format.strip() else {}),
                    "file_name": file_name.strip(),
                    "content": content,
                },
            }
            return
        if obj.get("action") == "edit_file":
            output_dir = obj.get("output_dir")
            raw_file_obj = obj.get("file")
            if not (isinstance(output_dir, str) and output_dir.strip()):
                return
            if not isinstance(raw_file_obj, dict):
                return
            file_obj = cast(dict[str, object], raw_file_obj)
            file_name = file_obj.get("file_name")
            if not (isinstance(file_name, str) and file_name.strip()):
                return
            replacements = {key: value for key, value in file_obj.items() if key.startswith("replacement_")}
            if not replacements:
                return
            parsed_replacements: dict[str, dict[str, str]] = {}
            for key, raw_value in replacements.items():
                if not isinstance(raw_value, dict):
                    return
                value = cast(dict[str, object], raw_value)
                find_text = value.get("find")
                replace_with = value.get("replace_with")
                line_num_ref = value.get("line_num_ref")
                if not (isinstance(find_text, str) and find_text):
                    return
                if not isinstance(replace_with, str):
                    return
                if isinstance(line_num_ref, bool):
                    return
                if isinstance(line_num_ref, int):
                    line_num_ref_str = str(line_num_ref)
                elif isinstance(line_num_ref, float) and line_num_ref.is_integer():
                    line_num_ref_str = str(int(line_num_ref))
                elif isinstance(line_num_ref, str) and line_num_ref.strip():
                    line_num_ref_str = line_num_ref.strip()
                else:
                    return
                parsed_replacements[key] = {"find": find_text, "replace_with": replace_with, "line_num_ref": line_num_ref_str}
            edit_file_obj = {
                "action": "edit_file",
                "output_dir": output_dir.strip(),
                "file": {"file_name": file_name.strip(), **parsed_replacements},
            }
            return
        if obj.get("action") == "rename":
            path = obj.get("path")
            new_name = obj.get("new_name")
            if not (isinstance(path, str) and path.strip()):
                return
            if not (isinstance(new_name, str) and new_name.strip()):
                return
            rename_obj = {"action": "rename", "path": path.strip(), "new_name": new_name.strip()}
            return
        if obj.get("action") == "delete":
            path = obj.get("path")
            if isinstance(path, str) and path.strip():
                delete_obj = {
                    "action": "delete",  # FIXED: Now includes the action key
                    "path": path.strip(),
                }
            return
        if obj.get("action") == "make_dir":
            path = obj.get("path")
            if isinstance(path, str) and path.strip():
                make_dir_obj = {"action": "make_dir", "path": path.strip()}
            return
        if obj.get("action") == "no_edit":
            no_edit_obj = dict(obj)
            return
        nested_edits = obj.get("edits")

        if obj.get("action"):
            edits.append(obj)
        elif isinstance(nested_edits, list):
            for item in nested_edits:
                if is_json_object(item):
                    collect_one(item)


    for parsed in parsed_blocks:
        if isinstance(parsed, list):
            for item in parsed:
                if is_json_object(item):
                    collect_one(item)
        elif is_json_object(parsed):
            collect_one(parsed)

    graph_edits: list[GraphEdit] = []

    for raw_edit in edits:
        try:
            graph_edits.append(GraphEdit.model_validate(raw_edit))
        except ValidationError:
            continue

    actions = ParsedActions(
        # GraphEdit actions
        edits=graph_edits,
        # Other Tool calls
        read_file=list(dict.fromkeys(read_file_paths)),
        read_code_block_ids=list(dict.fromkeys(read_code_block_ids)),
        read_current_workflow=read_current_workflow_requested,
        web_search=web_search_query,
        web_search_max_results=web_search_max_results,
        browse_url=browse_url,
        github=github_obj,
        report=report_obj,
        run_workflow=run_workflow_obj,
        grep=grep_obj,
        formulas_calc=formulas_calc_obj,
        delegate_request=delegate_request_obj,
        send_message=send_messages,
        get_unread=get_unreads,
        calendar=calendar_obj,
        clone_role=clone_role_obj,
        rag_search=rag_search_obj,
        list_dir=list_dir_obj,
        new_file=new_file_obj,
        edit_file=edit_file_obj,
        rename=rename_obj,
        delete=delete_obj,
        make_dir=make_dir_obj,
        no_edit=no_edit_obj,
    )

    return ParserOutput(actions=actions)


def parse_workflow_edits(content: str) -> ParserOutput:
    """Alias for parse_action_blocks for backward compatibility."""
    return parse_action_blocks(content)
