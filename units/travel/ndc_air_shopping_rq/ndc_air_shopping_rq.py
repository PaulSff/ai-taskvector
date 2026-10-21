from __future__ import annotations

from typing import Any

import requests
from requests import Response
from requests.exceptions import RequestException, Timeout

from core.schemas.primitives import Data, Output
from units.registry import UnitSpec, register_unit

NDC_AIR_SHOPING_RQ_INPUT_PORTS = [("xml_request", "str")]
NDC_AIR_SHOPING_RQ_OUTPUT_PORTS = [("xml_response", "str"), ("error", "str")]


def _coerce_headers(value: Any) -> dict[str, str]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise TypeError("headers must be a JSON object/dict")
    return {str(k): str(v) for k, v in value.items()}


def _send_request(
    url: str,
    xml_body: str,
    username: str | None,
    password: str | None,
    timeout: float,
    headers: dict[str, str],
    retries: int,
    retry_delay: float,
) -> Response:
    session = requests.Session()

    last_error: Exception | None = None
    for attempt in range(retries + 1):
        try:
            auth: tuple[str, str] | None
            if username is not None and password is not None:
                auth = (username, password)
            else:
                auth = None

            response = session.post(
                url,
                data=xml_body.encode("utf-8"),
                headers=headers,
                auth=auth,
                timeout=timeout,
            )
            return response
        except (Timeout, RequestException) as exc:
            last_error = exc
            if attempt >= retries:
                raise
            if retry_delay > 0:
                import time

                time.sleep(retry_delay)

    raise last_error or RuntimeError("request failed")


def _ndc_air_shopping_rq_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
) -> Output:
    raw = inputs.get("xml_request")

    if raw is None or str(raw).strip() == "":
        return {"xml_response": None, "error": "missing xml_request"}, state

    try:
        url = params.get("url")
        if not isinstance(url, str) or not url.strip():
            raise TypeError("url must be a non-empty string")

        username = params.get("username")
        password = params.get("password")

        timeout_raw = params.get("timeout", 30)
        if not isinstance(timeout_raw, (int, float, str)):
            raise TypeError("timeout must be a number or numeric string")
        timeout = float(timeout_raw)

        retries_raw = params.get("retries", 2)
        if not isinstance(retries_raw, (int, str)):
            raise TypeError("retries must be an int or numeric string")
        retries = int(retries_raw)

        retry_delay_raw = params.get("retry_delay", 1.0)
        if not isinstance(retry_delay_raw, (int, float, str)):
            raise TypeError("retry_delay must be a number or numeric string")
        retry_delay = float(retry_delay_raw)


        headers = _coerce_headers(params.get("headers"))
        headers.setdefault("Content-Type", "application/xml")
        headers.setdefault("Accept", "application/xml")

        if isinstance(raw, bytes):
            xml_body = raw.decode("utf-8")
        else:
            xml_body = str(raw)

        response = _send_request(
            url=url,
            xml_body=xml_body,
            username=str(username) if username is not None else None,
            password=str(password) if password is not None else None,
            timeout=timeout,
            headers=headers,
            retries=retries,
            retry_delay=retry_delay,
        )

        if response.ok:
            return {"xml_response": response.text, "error": ""}, state

        return {
            "xml_response": None,
            "error": f"HTTP {response.status_code}: {response.text}",
        }, state

    except (TypeError, ValueError, RequestException, Timeout) as exc:
        return {"xml_response": None, "error": str(exc)}, state


def register_ndc_air_shopping_rq() -> None:
    register_unit(
        UnitSpec(
            type_name="NdcAirShoppingRQ",
            input_ports=NDC_AIR_SHOPING_RQ_INPUT_PORTS,
            output_ports=NDC_AIR_SHOPING_RQ_OUTPUT_PORTS,
            step_fn=_ndc_air_shopping_rq_step,
            environment_tags=["travel"],
            environment_tags_are_agnostic=False,
            description=(
                "Send NDC AirShoppingRQ XML to an endpoint with retry logic. "
                "Params: url, username, password, timeout, headers, retries, retry_delay."
            ),
        )
    )


__all__ = [
    "NDC_AIR_SHOPING_RQ_INPUT_PORTS",
    "NDC_AIR_SHOPING_RQ_OUTPUT_PORTS",
    "register_ndc_air_shopping_rq",
]
