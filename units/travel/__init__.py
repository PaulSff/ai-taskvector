"""Environment "travel" units (scaffolded by list_environment). See README.md."""
from __future__ import annotations

import logging

from units.registry import UNIT_REGISTRY
from units.travel.build_flight_cal import register_build_flight_cal
from units.travel.json2ndc_xml import register_ndc_json_to_xml
from units.travel.ndc_air_shopping_rq import register_ndc_air_shopping_rq
from units.travel.ndc_xml2json import register_ndc_xml_to_json

logger = logging.getLogger(__name__)

_TRAVEL_TYPE_NAMES = (
    "NdcAirShoppingRQ",
    "NdcJsonToXml",
    "NdcXmlToJson",
    "BuildFlightCal",
)

def register_travel_units() -> None:
    """Register units for travel. Add register_* calls as you add units under units/travel/."""
    register_ndc_json_to_xml()
    register_ndc_xml_to_json()
    register_ndc_air_shopping_rq()
    register_build_flight_cal()

    for name in _TRAVEL_TYPE_NAMES:
        spec = UNIT_REGISTRY.get(name)
        if spec is not None:
            spec.environment_tags = ["travel"]


def _register_travel_env_loader() -> None:
    try:
        from units.env_loaders import register_env_loader
    except ImportError:
        logger.info("env_loaders not available; cannot register travel env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_env_loader for travel")
        raise

    try:
        from units.travel import register_travel_units
    except ImportError:
        logger.info("units.travel not available; cannot register travel env loader")
        return
    except Exception:
        logger.exception("Unexpected error importing register_travel_units for travel")
        raise

    try:
        register_env_loader("travel", register_travel_units)
    except Exception:
        logger.exception("Failed to register travel env loader")
        raise

_register_travel_env_loader()

__all__ = ["register_travel_units"]
