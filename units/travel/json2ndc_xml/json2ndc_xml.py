from __future__ import annotations

import json
from json import JSONDecodeError
from os import PathLike
from pathlib import Path

from lxml.etree import Element, tostring

from core.schemas.primitives import Data, Output
from units.registry import UnitSpec, register_unit

NDC_JSON_TO_XML_INPUT_PORTS = [("data", "JsonValue")]
NDC_JSON_TO_XML_OUTPUT_PORTS = [("xml", "str"), ("error", "str")]


def _load_sequences(value: str | PathLike[str] | None) -> dict[str, list[str]]:
    if value is None or str(value).strip() == "":
        raise ValueError("missing sequence_file parameter")

    path = Path(value)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise TypeError("sequence file must contain a JSON object")

    return data


def _escape_text(value: str) -> str:
    return (
        value.replace("\\", "\\\\")
        .replace("\n", "\\n")
        .replace("\t", "\\t")
        .replace('"', '\\"')
    )


def _build_element(
    key: str,
    value: Data,
    sequences: dict[str, list[str]],
    xpath: str,
) -> Element:
    el = Element(key)

    if "$" in value and isinstance(value["$"], dict):
        attrs = value["$"]
        for attr, attr_value in attrs.items():
            el.set(attr, str(attr_value))

    if "_" in value:
        el.text = _escape_text(str(value["_"]))
        return el

    child_keys = [k for k in value if k not in {"$", "_"}]

    ordered_keys: list[str] = []
    seq = sequences.get(xpath, [])
    for k in seq:
        if k in child_keys:
            ordered_keys.append(k)
    if len(ordered_keys) != len(child_keys):
        ordered_keys = child_keys

    for child_key in ordered_keys:
        child_value = value[child_key]
        child_xpath = f"{xpath}{child_key}/"

        if isinstance(child_value, list):
            for item in child_value:
                if isinstance(item, dict):
                    el.append(_build_element(child_key, item, sequences, child_xpath))
        elif isinstance(child_value, dict):
            el.append(_build_element(child_key, child_value, sequences, child_xpath))

    return el


def _ndc_json_to_xml_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    raw = inputs.get("data")

    if raw is None:
        return {"xml": None, "error": "missing data"}, state

    if isinstance(raw, dict):
        if "data" in raw:
            raw = raw["data"]
        elif "parsed" in raw:
            raw = raw["parsed"]

    try:
        sequence_file = params.get("sequence_file")
        if not isinstance(sequence_file, (str, PathLike)):
            raise TypeError("sequence_file must be a string or path-like value")

        sequences = _load_sequences(sequence_file)

        if isinstance(raw, bytes):
            raw = raw.decode("utf-8")

        if isinstance(raw, str):
            json_obj = json.loads(raw)
        else:
            json_obj = raw

        if not isinstance(json_obj, dict) or len(json_obj) != 1:
            raise TypeError("input JSON must contain exactly one root element")

        root_key = next(iter(json_obj))
        root_val = json_obj[root_key]
        if not isinstance(root_val, dict):
            raise TypeError("root element must be an object")

        root = _build_element(root_key, root_val, sequences, f"{root_key}/")
        xml = tostring(root, encoding="unicode")
        return {"xml": xml, "error": ""}, state

    except (TypeError, ValueError, JSONDecodeError) as exc:
        return {"xml": None, "error": str(exc)}, state


def register_ndc_json_to_xml() -> None:
    register_unit(
        UnitSpec(
            type_name="NdcJsonToXml",
            input_ports=NDC_JSON_TO_XML_INPUT_PORTS,
            output_ports=NDC_JSON_TO_XML_OUTPUT_PORTS,
            step_fn=_ndc_json_to_xml_step,
            environment_tags=["travel"],
            environment_tags_are_agnostic=False,
            description=(
                "Convert NDC JSON to XML using a version-specific sequence "
                "metadata file. Params: sequence_file."
            ),
        )
    )


__all__ = [
    "NDC_JSON_TO_XML_INPUT_PORTS",
    "NDC_JSON_TO_XML_OUTPUT_PORTS",
    "register_ndc_json_to_xml",
]
