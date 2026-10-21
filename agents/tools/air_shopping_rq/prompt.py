"""AirShoppingRQ: Request low fare flight calendar for a specific range of dates via NDC IATA protocol"""

TOOL_ACTION_PROMPT_LINE = """- air_shopping_rq: Request available flights prices for a specific range of dates via NDC IATA protocol:
    {
      "action": "get_low_fare_flight_calendar",
      "method":
        {
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
                      "AirportCode": {
                        "_": "MOW"
                      },
                      "Date": {
                        "_": "2026-10-09"
                      }
                    },
                    "Arrival": {
                      "AirportCode": {
                        "_": "LED"
                      }
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
                      "AirportCode": {
                        "_": "LED"
                      },
                      "Date": {
                        "_": "2026-10-22"
                      }
                    },
                    "Arrival": {
                      "AirportCode": {
                        "_": "MOW"
                      }
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
                    "$": {
                      "PassengerID": "PAX_ADT"
                    },
                    "PTC": {
                      "_": "ADT"
                    }
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
                          "$": {
                            "MetadataKey": "LG1"
                          },
                          "Code_ISO": {
                            "_": "ru"
                          }
                        }
                      ]
                    }
                  }
                ]
              }
            }
          }
        }
      }

 Use IATA codes to construct the request. Passenger Type Codes (PTC):
     ADT	Adult	Standard adult passenger (usually 12+ years).
     CHD	Child	Passenger aged 2 to 11 years.
     INF	Infant	Passenger under 2 years (with or without a seat).
     STU	Student	Passengers with valid student identification.
     MIL	Military	Active duty or retired military personnel.
     SNR	Senior	Passengers over a certain age (e.g., 65+).
     YTH	Youth	Passengers in a specific age bracket (e.g., 12–25).
"""
