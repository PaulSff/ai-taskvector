# Run:
# pytest units/data_bi/ndc_xml2json/test_ndc_xml2json.py -vv --singleton_file units/data_bi/ndc_xml2json/singletons/singletons-172.json
# or if you would like the output printed:
# pytest units/data_bi/ndc_xml2json/test_ndc_xml2json.py -s --singleton_file units/data_bi/ndc_xml2json/singletons/singletons-172.json
import json
from pathlib import Path

import pytest

from .ndc_xml2json import _ndc_xml_to_json_step

XML_INPUT = """<?xml version="1.0" encoding="UTF-8"?>
<AirShoppingRQ xmlns="http://www.iata.org/IATA/EDIST/2017.2" AsynchronousAllowedInd="true" Version="17.2" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">
	<Document/>
	<CoreQuery>
    <OriginDestinations>
      <OriginDestination>
        <Departure>
          <AirportCode>MOW</AirportCode>
          <Date>2026-10-09</Date>
        </Departure>
        <Arrival>
          <AirportCode>LED</AirportCode>
        </Arrival>
        <CalendarDates DaysBefore="7" DaysAfter="7"/>
      </OriginDestination>
       <OriginDestination>
        <Departure>
          <AirportCode>LED</AirportCode>
          <Date>2026-10-22</Date>
        </Departure>
        <Arrival>
          <AirportCode>MOW</AirportCode>
        </Arrival>
        <CalendarDates DaysBefore="7" DaysAfter="7"/>
      </OriginDestination>
   </OriginDestinations>
	</CoreQuery>
	<DataLists>
		<PassengerList>
			<Passenger PassengerID="PAX_ADT">
				<PTC>ADT</PTC>
			</Passenger>
		</PassengerList>
	</DataLists>
	<Metadata>
		<Other>
			<OtherMetadata>
				<LanguageMetadatas>
					<LanguageMetadata MetadataKey="LG1">
						<Code_ISO>ru</Code_ISO>
					</LanguageMetadata>
				</LanguageMetadatas>
			</OtherMetadata>
		</Other>
	</Metadata>
</AirShoppingRQ>"""


@pytest.fixture
def singleton_file(pytestconfig):
    return pytestconfig.getoption("--singleton_file")


def test_ndc_xml_to_json_converts_airshoppingrq(singleton_file: Path):
    # Explicitly typing these as dict[str, object] prevents the invariance error
    params: dict[str, object] = {"singleton_file": str(singleton_file)}
    inputs: dict[str, object] = {"data": XML_INPUT}
    state: dict[str, object] = {}

    output, new_state = _ndc_xml_to_json_step(params, inputs, state, dt=0.0)

    # --- Print the output ---
    print("\n\nACTUAL JSON OUTPUT:")
    print(json.dumps(output["json"], indent=2))
    print("\n" + "="*30 + "\n")
    # -----------------------

    assert new_state == {}
    assert output["error"] == ""

    assert output["json"] == {
        "AirShoppingRQ": {
            "$": {
                "AsynchronousAllowedInd": "true",
                "Version": "17.2",
            },
            "Document": {},
            "CoreQuery": {
                "OriginDestinations": {
                    "OriginDestination": [
                        {
                            "Departure": {
                                "AirportCode": {"_": "MOW"},
                                "Date": {"_": "2026-10-09"},
                            },
                            "Arrival": {
                                "AirportCode": {"_": "LED"},
                            },
                            "CalendarDates": {
                                "$": {
                                    "DaysBefore": "7",
                                    "DaysAfter": "7",
                                }
                            },
                        },
                        {
                            "Departure": {
                                "AirportCode": {"_": "LED"},
                                "Date": {"_": "2026-10-22"},
                            },
                            "Arrival": {
                                "AirportCode": {"_": "MOW"},
                            },
                            "CalendarDates": {
                                "$": {
                                    "DaysBefore": "7",
                                    "DaysAfter": "7",
                                }
                            },
                        },
                    ]
                }
            },
            "DataLists": {
                "PassengerList": {
                    # Wrapped in a list []
                    "Passenger": [
                        {
                            "$": {"PassengerID": "PAX_ADT"},
                            "PTC": {"_": "ADT"},
                        }
                    ]
                }
            },
            "Metadata": {
                "Other": {
                    # Wrapped in a list []
                    "OtherMetadata": [
                        {
                            "LanguageMetadatas": {
                                # Wrapped in a list []
                                "LanguageMetadata": [
                                    {
                                        "$": {"MetadataKey": "LG1"},
                                        "Code_ISO": {"_": "ru"},
                                    }
                                ]
                            }
                        }
                    ]
                }
            },
        }
    }
