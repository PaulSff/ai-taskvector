"""
NdcXmlToJson unit: convert NDC XML to the AIR Tech Zone converter's JSON shape.

Params:
    singleton_file (str): Path to the version-specific singleton JSON file,
        e.g. "singletons/singletons-172.json".

Input:
    data: XML text or bytes

Outputs:
    json: Converted Python dict/list
    error: Empty string on success, otherwise an error message
"""
from __future__ import annotations

import json
from os import PathLike
from pathlib import Path

from lxml.etree import ParserError, XMLParser, XMLSyntaxError, _Element, fromstring

from core.schemas.primitives import Data, Output
from units.registry import UnitSpec, register_unit

NDC_XML_TO_JSON_INPUT_PORTS = [("data", "Any")]
NDC_XML_TO_JSON_OUTPUT_PORTS = [("json", "JsonValue"), ("error", "str")]


def _qualified_name(name: str, nsmap: dict[str | None, str], prefix: str | None) -> str:
    """Format an lxml name like a DOM nodeName, retaining a namespace prefix."""
    if not name.startswith("{"):
        return name

    namespace, local_name = name[1:].split("}", 1)
    if prefix:
        return f"{prefix}:{local_name}"

    # A default namespace does not add a prefix to DOM nodeName.
    if nsmap.get(None) == namespace:
        return local_name

    # Find a declared prefix for the namespace, if available.
    for candidate_prefix, uri in nsmap.items():
        if uri == namespace and candidate_prefix:
            return f"{candidate_prefix}:{local_name}"

    return local_name


def _element_name(element: _Element) -> str:
    return _qualified_name(element.tag, element.nsmap or {}, element.prefix)


def _attribute_name(element: _Element, name: str) -> str:
    # lxml stores namespaced attributes as "{namespace-uri}local-name".
    if not name.startswith("{"):
        return name

    namespace, local_name = name[1:].split("}", 1)
    for prefix, uri in (element.nsmap or {}).items():
        if uri == namespace and prefix:
            return f"{prefix}:{local_name}"
    return local_name


def _element_children(element: _Element) -> list[_Element]:
    # Comments and processing instructions have non-string tags in lxml.
    return [
        child
        for child in element
        if isinstance(child.tag, str)
    ]


def _text_content_like_reference(element: _Element) -> str | None:
    """
    Match the reference converter's basic behavior:
    - If the element has element children, treat it as a parent, not a text leaf.
    - Otherwise, if it contains text, return its text content.
    """
    if _element_children(element):
        return None

    # lxml stores direct text in .text and trailing text in child .tail.
    parts: list[str] = []
    if element.text is not None:
        parts.append(element.text)

    for child in element:
        if child.tail is not None:
            parts.append(child.tail)

    if not parts:
        return None

    return "".join(parts)


def _convert_element(
    element: _Element,
    xpath: str,
    singletons: set[str],
) -> Data:
    result: Data = {}

    # Attributes are placed under "$".
    if element.attrib:
        result["$"] = {
            _attribute_name(element, name): value
            for name, value in element.attrib.items()
        }

    text = _text_content_like_reference(element)
    if text is not None:
        result["_"] = text
        return result

    children = _element_children(element)
    seen_names: set[str] = set()

    # Group siblings by name, preserving first-appearance order.
    for child in children:
        name = _element_name(child)
        if name in seen_names:
            continue
        seen_names.add(name)

        child_xpath = f"{xpath}{name}/"
        matching_children = [
            candidate
            for candidate in children
            if _element_name(candidate) == name
        ]

        if child_xpath in singletons:
            # NDC schema singletons should occur at most once.
            result[name] = _convert_element(
                matching_children[0],
                child_xpath,
                singletons,
            )
        else:
            result[name] = [
                _convert_element(candidate, child_xpath, singletons)
                for candidate in matching_children
            ]

    return result


def _load_singletons(value: str | PathLike[str] | None) -> set[str]:
    if value is None or str(value).strip() == "":
        raise ValueError("missing singleton_file parameter")

    path = Path(value)
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, list) or not all(isinstance(item, str) for item in data):
        raise TypeError("singleton file must contain a JSON array of strings")

    return set(data)


def _ndc_xml_to_json_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    raw = inputs.get("data")

    if raw is None:
        return {"json": None, "error": "missing data"}, state

    # Accept common upstream wrapper shapes.
    if isinstance(raw, dict):
        if "data" in raw:
            raw = raw["data"]
        elif "parsed" in raw:
            raw = raw["parsed"]

    try:
        singleton_file = params.get("singleton_file")
        if not isinstance(singleton_file, (str, PathLike)):
            raise TypeError("singleton_file must be a string or path-like value")

        singletons = _load_singletons(singleton_file)

        if isinstance(raw, bytes):
            xml_bytes = raw
        else:
            xml_bytes = str(raw).encode("utf-8")

        if not xml_bytes.strip():
            return {"json": None, "error": "empty XML input"}, state

        parser = XMLParser(
            recover=False,
            remove_comments=False,
            resolve_entities=False,
            no_network=True,
        )
        root = fromstring(xml_bytes, parser=parser)

        root_name = _element_name(root)
        converted = {
            root_name: _convert_element(
                root,
                f"{root_name}/",
                singletons,
            )
        }

        return {"json": converted, "error": ""}, state

    except (XMLSyntaxError, ParserError) as exc:
            return {"json": None, "error": str(exc)}, state


def register_ndc_xml_to_json() -> None:
    register_unit(
        UnitSpec(
            type_name="NdcXmlToJson",
            input_ports=NDC_XML_TO_JSON_INPUT_PORTS,
            output_ports=NDC_XML_TO_JSON_OUTPUT_PORTS,
            step_fn=_ndc_xml_to_json_step,
            environment_tags=["travel"],
            environment_tags_are_agnostic=False,
            description=(
                "Convert NDC XML to JSON using a version-specific singleton "
                "metadata file. Params: singleton_file."
            ),
        )
    )


__all__ = [
    "NDC_XML_TO_JSON_INPUT_PORTS",
    "NDC_XML_TO_JSON_OUTPUT_PORTS",
    "register_ndc_xml_to_json",
]
