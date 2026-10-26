"""
Expected input is a standard NDC AirShoppingRS shape like this:

{
  "ns2:AirShoppingRS": {
    "$": {
      "EchoToken": "0.2.0",
      "TimeStamp": "2026-10-26T10:14:33Z",
      "Version": "17.2"
    },
    "ns2:Document": [
      {}
    ],
    "ns2:Success": [
      {}
    ],
    "ns2:ShoppingResponseID": [
      {
        "ns2:Owner": [
          {
            "_": "APD"
          }
        ],
        "ns2:ResponseID": [
          {
            "_": "APD1fb6eeeb-fcee-4dc0-88d1-a4224d0bb8b0"
          }
        ]
      }
    ],
    "ns2:OffersGroup": [..]
..

    "ns2:FlightList": [..]
 ..

    "ns2:FlightSegmentList": [..]
..

    "ns2:PriceCalendar": [..]

..
    "ns2:PriceClassList": [..]

Output:

{
  "trip": "MOW -> LED -> MOW (roundtrip)",

  "price_calendar": [
    {
      "OfferID": "OF1_VKOLED2611022611156R",
      "Flights": {
           "outbound": "FL1_VKOLED_261102 2026-11-02 18:00 -> 19:25",
           "return": "FL2_LEDVKO_261115 2026-11-15 16:00 -> 17:25"
     }
      "validatingCarrier": "6R",
      "cabinClass": "Economy",
      "passengers": "1 ADT"
      "totalPrice": "1694.00 EUR",
    },
    {
    ...
    }
  ]
}

"""
from __future__ import annotations

import json
import logging
import re
from typing import Any

from core.schemas.primitives import Data, safe_int
from services.logging import setup_colored_logging
from units.registry import UnitSpec, register_unit

BUILD_FLIGHT_CAL_INPUT_PORTS = [("data", "JsonValue"), ("file_path", "str")]
BUILD_FLIGHT_CAL_OUTPUT_PORTS = [("item", "JsonValue"), ("error", "str")]

_DEFAULT_MAX_OFFERS = 200
_PASSENGER_REF_RE = re.compile(r"(?:^|[_-])([A-Z]{2,5})(?:$|[_-])")

logger = setup_colored_logging(logging.DEBUG)


def _as_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, (dict, list)):
        try:
            return json.dumps(v, ensure_ascii=False)
        except (TypeError, ValueError):
            return str(v)
    return str(v).strip()


def _scalar_text(v: Any) -> str:
    if v is None:
        return ""
    if isinstance(v, dict):
        return _as_text(v.get("_"))
    if isinstance(v, list):
        return _scalar_text(v[0]) if v else ""
    return _as_text(v)


def _first(obj: Any, path: list[Any]) -> Any:
    cur = obj
    for key in path:
        if isinstance(cur, dict):
            cur = cur.get(key)
        elif isinstance(cur, list):
            if not cur:
                return None
            if isinstance(key, int) and 0 <= key < len(cur):
                cur = cur[key]
            else:
                cur = cur[0]
        else:
            return None
    return cur


def _safe_clamped_int(value: object, default: int, low: int, high: int) -> int:
    n = safe_int(value)
    if n is None:
        n = default
    return max(low, min(n, high))


def _extract_passenger_code(ref: str) -> str:
    ref = _as_text(ref)
    if not ref:
        return ""

    matches = _PASSENGER_REF_RE.findall(ref)
    if matches:
        return matches[-1]

    fallback = re.findall(r"[A-Z]{2,5}", ref)
    return fallback[-1] if fallback else ""


def _find_all_keys(obj: Any, target: str) -> list[Any]:
    found: list[Any] = []
    if isinstance(obj, dict):
        for k, v in obj.items():
            if k == target:
                found.append(v)
            found.extend(_find_all_keys(v, target))
    elif isinstance(obj, list):
        for item in obj:
            found.extend(_find_all_keys(item, target))
    return found


def _collect_flight_map(data: dict[str, Any]) -> dict[str, dict[str, str]]:
    flight_map: dict[str, dict[str, str]] = {}
    segment_index: dict[str, dict[str, str]] = {}

    flight_lists = _find_all_keys(data, "ns2:FlightList")
    for flight_list in flight_lists:
        if not isinstance(flight_list, list):
            flight_list = [flight_list]

        for group in flight_list:
            if not isinstance(group, dict):
                continue
            for flight in group.get("ns2:Flight", []) or []:
                if not isinstance(flight, dict):
                    continue

                flight_key = _as_text(flight.get("$", {}).get("FlightKey"))
                seg_refs = [
                    _as_text(ref.get("_"))
                    for ref in (flight.get("ns2:SegmentReferences", []) or [])
                    if isinstance(ref, dict) and _as_text(ref.get("_"))
                ]

                if flight_key:
                    flight_map[flight_key] = {
                        "segment_ref": seg_refs[0] if seg_refs else ""
                    }

    segment_lists = _find_all_keys(data, "ns2:FlightSegmentList")
    for segment_list in segment_lists:
        if not isinstance(segment_list, list):
            segment_list = [segment_list]

        for group in segment_list:
            if not isinstance(group, dict):
                continue
            for seg in group.get("ns2:FlightSegment", []) or []:
                if not isinstance(seg, dict):
                    continue

                seg_key = _as_text(seg.get("$", {}).get("SegmentKey"))
                dep = (seg.get("ns2:Departure", []) or [{}])[0]
                arr = (seg.get("ns2:Arrival", []) or [{}])[0]
                mkt = (seg.get("ns2:MarketingCarrier", []) or [{}])[0]

                dep_airport = _scalar_text((dep or {}).get("ns2:AirportCode"))
                dep_date = _scalar_text((dep or {}).get("ns2:Date"))
                dep_time = _scalar_text((dep or {}).get("ns2:Time"))

                arr_airport = _scalar_text((arr or {}).get("ns2:AirportCode"))
                arr_date = _scalar_text((arr or {}).get("ns2:Date"))
                arr_time = _scalar_text((arr or {}).get("ns2:Time"))

                carrier = _scalar_text((mkt or {}).get("ns2:AirlineID"))
                flight_number = _scalar_text((mkt or {}).get("ns2:FlightNumber"))

                if seg_key:
                    segment_index[seg_key] = {
                        "dep_airport": dep_airport,
                        "dep_date": dep_date,
                        "dep_time": dep_time,
                        "arr_airport": arr_airport,
                        "arr_date": arr_date,
                        "arr_time": arr_time,
                        "carrier": carrier,
                        "flight_number": flight_number,
                    }

    for flight_key, info in flight_map.items():
        seg_ref = info.get("segment_ref", "")
        seg_info = segment_index.get(seg_ref)
        if seg_info:
            info.update(seg_info)
        else:
            logger.warning("Missing segment for flight_key=%s seg_ref=%s", flight_key, seg_ref)

    return flight_map


def _build_flight_str(flight_info: dict[str, str], flight_ref: str) -> str:
    if not flight_info:
        return _as_text(flight_ref)

    dep_airport = flight_info.get("dep_airport", "")
    arr_airport = flight_info.get("arr_airport", "")
    dep_date = flight_info.get("dep_date", "")
    dep_time = flight_info.get("dep_time", "")
    arr_time = flight_info.get("arr_time", "")

    if dep_airport and arr_airport and dep_date and dep_time and arr_time:
        return f"{flight_ref} {dep_date} {dep_time} -> {arr_time}"
    if dep_airport and arr_airport:
        return f"{flight_ref} {dep_airport} -> {arr_airport}"
    return _as_text(flight_ref)


def _extract_trip(data: dict[str, Any]) -> str:
    offers_group = (data.get("ns2:AirShoppingRS", {}) or {}).get("ns2:OffersGroup", []) or []
    first_offer = None

    for group in offers_group:
        for ao in group.get("ns2:AirlineOffers", []) or []:
            offer_list = ao.get("ns2:Offer", []) or []
            if offer_list:
                first_offer = offer_list[0]
                break
        if first_offer:
            break

    if not first_offer:
        return ""

    flights = []
    for f in first_offer.get("ns2:FlightsOverview", []) or []:
        for ref in f.get("ns2:FlightRef", []) or []:
            rid = _as_text(ref.get("_"))
            if rid:
                flights.append(rid)

    if len(flights) < 1:
        return ""

    dep = flights[0].split("_")[1][:3] if "_" in flights[0] and len(flights[0].split("_")) > 1 else ""
    final_arr = flights[-1].split("_")[1][3:6] if "_" in flights[-1] and len(flights[-1].split("_")) > 1 else ""
    if dep and final_arr:
        trip_type = "roundtrip" if dep == final_arr else "oneway"
        return f"{dep} -> {final_arr} ({trip_type})"
    return ""


def _extract_offer_by_id(data: dict[str, Any]) -> dict[str, dict[str, Any]]:
    offers_by_id: dict[str, dict[str, Any]] = {}
    offers_group = (data.get("ns2:AirShoppingRS", {}) or {}).get("ns2:OffersGroup", []) or []

    for group in offers_group:
        for airline_offers in group.get("ns2:AirlineOffers", []) or []:
            for offer in airline_offers.get("ns2:Offer", []) or []:
                offer_id = _as_text(offer.get("$", {}).get("OfferID"))
                if offer_id:
                    offers_by_id[offer_id] = offer

    return offers_by_id


def _extract_price_calendar(data: dict[str, Any]) -> list[dict[str, Any]]:
    price_calendar = _find_all_keys(data, "ns2:PriceCalendar")
    if not price_calendar:
        logger.info("PriceCalendar not found")
        return []

    rows: list[dict[str, Any]] = []
    seen_refs: set[str] = set()

    offers_by_id = _extract_offer_by_id(data)
    logger.info("Found %d offers in OffersGroup", len(offers_by_id))

    flight_map = _collect_flight_map(data)
    logger.info("Found %d flight refs in FlightList/FlightSegmentList", len(flight_map))

    for pc_idx, pc in enumerate(price_calendar):
        if isinstance(pc, list):
            pcs = pc
        else:
            pcs = [pc]

        logger.info("Found %d PriceCalendar nodes at index %d", len(pcs), pc_idx)

        for node_idx, node in enumerate(pcs):
            if not isinstance(node, dict):
                logger.warning("PriceCalendar[%d][%d] is not a dict: %r", pc_idx, node_idx, node)
                continue

            total_prices = node.get("ns2:TotalPrice", []) or []
            ptcs = node.get("ns2:PTC", []) or []

            logger.info(
                "PriceCalendar[%d][%d]: total_prices=%d ptcs=%d",
                pc_idx,
                node_idx,
                len(total_prices),
                len(ptcs),
            )

            passenger_parts = []
            for p_idx, ptc in enumerate(ptcs):
                if not isinstance(ptc, dict):
                    logger.warning("PriceCalendar[%d][%d].PTC[%d] is not a dict: %r", pc_idx, node_idx, p_idx, ptc)
                    continue
                qty = _as_text(ptc.get("$", {}).get("Quantity")) or "1"
                code_ptc = _as_text(ptc.get("_"))
                if code_ptc:
                    passenger_parts.append(f"{qty} {code_ptc}")
                else:
                    logger.warning("Missing PTC code at PriceCalendar[%d][%d].PTC[%d]", pc_idx, node_idx, p_idx)

            passengers = " + ".join(passenger_parts)

            for t_idx, total in enumerate(total_prices):
                if not isinstance(total, dict):
                    logger.warning("PriceCalendar[%d][%d].TotalPrice[%d] is not a dict: %r", pc_idx, node_idx, t_idx, total)
                    continue

                refs = _as_text(total.get("$", {}).get("refs"))
                amount = _as_text(total.get("_"))
                code = _as_text(total.get("$", {}).get("Code"))

                logger.info(
                    "PriceCalendar[%d][%d].TotalPrice[%d]: refs=%s amount=%s code=%s",
                    pc_idx,
                    node_idx,
                    t_idx,
                    refs,
                    amount,
                    code,
                )

                if not refs:
                    logger.warning("Skipping TotalPrice[%d] because refs is missing", t_idx)
                    continue
                if refs in seen_refs:
                    logger.info("Skipping duplicate refs=%s", refs)
                    continue
                seen_refs.add(refs)

                offer = offers_by_id.get(refs)
                if not offer:
                    logger.warning("No offer found for refs=%s", refs)
                    continue

                logger.info("Matched offer for refs=%s keys=%s", refs, list(offer.keys()))

                flights_overview = offer.get("ns2:FlightsOverview", []) or []
                flight_refs: list[str] = []
                for f in flights_overview:
                    if not isinstance(f, dict):
                        continue
                    for ref in f.get("ns2:FlightRef", []) or []:
                        rid = _as_text(ref.get("_"))
                        if rid:
                            flight_refs.append(rid)

                logger.info("OfferID=%s flight_refs=%s", refs, flight_refs)

                outbound_ref = flight_refs[0] if flight_refs else ""
                return_ref = flight_refs[1] if len(flight_refs) > 1 else ""

                outbound_info = flight_map.get(outbound_ref)
                return_info = flight_map.get(return_ref)

                if not outbound_info:
                    logger.warning("Missing outbound flight info for ref=%s", outbound_ref)
                if return_ref and not return_info:
                    logger.warning("Missing return flight info for ref=%s", return_ref)

                validating_carrier = _scalar_text(_first(offer, ["ns2:ValidatingCarrier"]))

                cabin_class = ""
                fare_details = offer.get("ns2:FareDetail", []) or []
                for fd in fare_details:
                    if not isinstance(fd, dict):
                        continue
                    components = fd.get("ns2:FareComponent", []) or []
                    for comp in components:
                        if not isinstance(comp, dict):
                            continue
                        cabin_class = _scalar_text(_first(comp, ["ns2:CabinType"]))
                        if cabin_class:
                            break
                    if cabin_class:
                        break

                offer_expires_at = _scalar_text(
                    _first(offer, ["ns2:TimeLimits", "ns2:OfferExpiration", "$", "DateTime"])
                )

                rows.append(
                    {
                        "OfferID": refs,
                        "Flights": {
                            "outbound": _build_flight_str(outbound_info or {}, outbound_ref),
                            "return": _build_flight_str(return_info or {}, return_ref),
                        },
                        "validatingCarrier": validating_carrier,
                        "cabinClass": cabin_class,
                        "passengers": passengers,
                        "totalPrice": f"{amount} {code}".strip(),
                        "offerExpiresAt": offer_expires_at,
                    }
                )

    logger.info("Built %d price_calendar rows", len(rows))
    return rows


def _build_flight_calendar_step(
    params: Data,
    inputs: Data,
    state: Data,
    dt: float,
):
    try:
        parsed = inputs.get("data")
        fp = ""

        fp_port = inputs.get("file_path")
        if isinstance(fp_port, str) and fp_port.strip():
            fp = fp_port.strip()

        _ = _safe_clamped_int(params.get("max_offers"), _DEFAULT_MAX_OFFERS, 1, 1000)

        if not isinstance(parsed, dict):
            return {"item": {}, "error": ""}, state

        item = {
            "trip": _extract_trip(parsed),
            "price_calendar": _extract_price_calendar(parsed),
            "metadata": {
                "file_path": fp,
                "origin": "airshopping-flatten-extract",
                "content_type": "application/json",
            },
        }

        return {"item": item, "error": ""}, state

    except (ValueError, TypeError) as e:
        return {"item": {}, "error": str(e)}, state


def register_build_flight_cal() -> None:
    register_unit(
        UnitSpec(
            type_name="BuildFlightCal",
            input_ports=BUILD_FLIGHT_CAL_INPUT_PORTS,
            output_ports=BUILD_FLIGHT_CAL_OUTPUT_PORTS,
            step_fn=_build_flight_calendar_step,
            environment_tags=["travel"],
            environment_tags_are_agnostic=False,
            description="Flattens AirShoppingRS into a single compact UI-like object.",
        )
    )


__all__ = [
    "BUILD_FLIGHT_CAL_INPUT_PORTS",
    "BUILD_FLIGHT_CAL_OUTPUT_PORTS",
    "register_build_flight_cal",
]
