# Run:
# pytest units/data_bi/json2ndc_xml/test_json2ndc_xml.py -vv --sequence_file units/data_bi/json2ndc_xml/sequences/sequences-172.json
# or if you need the output printed:
# # pytest units/data_bi/json2ndc_xml/test_json2ndc_xml.py -s --sequence_file units/data_bi/json2ndc_xml/sequences/sequences-172.json
from pathlib import Path

import pytest

from core.schemas.primitives import Data

from .json2ndc_xml import _ndc_json_to_xml_step

JSON_INPUT = {
    "AirShoppingRQ": {
        "$": {
            "AsynchronousAllowedInd": "true",
            "Version": "17.2"
        },
        "Document": {},
        "CoreQuery": {
            "OriginDestinations": {
                "OriginDestination": [
                    {
                        "Departure": {
                            "AirportCode": {"_": "MOW"},
                            "Date": {"_": "2026-10-09"}
                        },
                        "Arrival": {
                            "AirportCode": {"_": "LED"}
                        },
                        "CalendarDates": {
                            "$": {
                                "DaysBefore": "7",
                                "DaysAfter": "7"
                            }
                        }
                    },
                    {
                        "Departure": {
                            "AirportCode": {"_": "LED"},
                            "Date": {"_": "2026-10-22"}
                        },
                        "Arrival": {
                            "AirportCode": {"_": "MOW"}
                        },
                        "CalendarDates": {
                            "$": {
                                "DaysBefore": "7",
                                "DaysAfter": "7"
                            }
                        }
                    }
                ]
            }
        },
        "DataLists": {
            "PassengerList": {
                "Passenger": [
                    {
                        "$": {"PassengerID": "PAX_ADT"},
                        "PTC": {"_": "ADT"}
                    }
                ]
            }
        },
        "Metadata": {
            "Other": {
                "OtherMetadata": [
                    {
                        "LanguageMetadatas": {
                            "LanguageMetadata": [
                                {
                                    "$": {"MetadataKey": "LG1"},
                                    "Code_ISO": {"_": "ru"}
                                }
                            ]
                        }
                    }
                ]
            }
        }
    }
}

@pytest.fixture
def sequence_file(pytestconfig):
    """Retrieves the --sequence_file flag from the command line."""
    return pytestconfig.getoption("--sequence_file")

def test_ndc_json_to_xml_converts_correctly(sequence_file: Path):
    # 1. Prepare inputs
    params: Data = {"sequence_file": str(sequence_file)}
    inputs: Data = {"data": JSON_INPUT}
    state: Data = {}

    # 2. Execute the unit
    output, new_state = _ndc_json_to_xml_step(params, inputs, state, dt=0.0)

    # 3. Assertions
    assert new_state == {}
    assert output["error"] == ""

    xml_result = output["xml"]

    # FIX: Use isinstance(). This "proves" to the type checker that
    # xml_result is a string. Any line below this check will
    # treat xml_result as a 'str' instead of an 'object'.
    assert isinstance(xml_result, str), f"Expected xml result to be str, got {type(xml_result)}"

    # print the resulted XML
    print("\n\nGENERATED XML OUTPUT:\n", xml_result, "\n")

    # Now the type checker allows the 'in' operator
    assert '<AirShoppingRQ' in xml_result
    assert 'AsynchronousAllowedInd="true"' in xml_result
    assert 'Version="17.2"' in xml_result
    assert '<AirportCode>MOW</AirportCode>' in xml_result
    assert '<AirportCode>LED</AirportCode>' in xml_result
    assert 'DaysBefore="7"' in xml_result
    assert 'PassengerID="PAX_ADT"' in xml_result
    assert '<PTC>ADT</PTC>' in xml_result
    assert 'MetadataKey="LG1"' in xml_result
    assert '<Code_ISO>ru</Code_ISO>' in xml_result

def test_ndc_json_to_xml_handles_missing_data(sequence_file: Path):
    params: dict[str, object] = {"sequence_file": str(sequence_file)}
    inputs: dict[str, object] = {"data": None}
    state: dict[str, object] = {}

    output, _ = _ndc_json_to_xml_step(params, inputs, state, dt=0.0)
    assert output["error"] == "missing data"
    assert output["xml"] is None
