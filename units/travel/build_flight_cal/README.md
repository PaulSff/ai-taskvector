# BuildFlightCal Unit

A TaskVector unit that flattens complex NDC AirShoppingRS responses into a compact, UI-ready price calendar format.


## Overview

The `BuildFlightCal` unit is designed to handle the complexity of NDC (New Distribution Capability) airline shopping responses. It extracts essential pricing, flight timing, and routing information from a nested JSON structure (typically converted from XML) and produces a simplified 'Price Calendar' that can be easily displayed in a frontend application.


## Key Features

- **Data Flattening**: Converts deeply nested `ns2` namespaces into a flat list of offers.
- **Flight Resolution**: Maps flight references to actual segment data (Departure/Arrival airports, dates, and times).
- **Automatic Sorting**: Sorts the resulting price calendar by price in ascending order.
- **Smart Persistence**: Saves the output to a JSON file with a descriptive name based on the trip route and date range (e.g., `ORIGIN_DEST_DATE_RANGE.json`).
- **Trip Type Detection**: Automatically detects if the itinerary is a 'roundtrip' or 'oneway'.


## Input/Output Specification

**Input Port (`data`)**: 
Expects a standard `AirShoppingRS` JSON object containing `OffersGroup`, `FlightList`, `FlightSegmentList`, and `PriceCalendar`.

**Output Port (`item`)**: 
Returns a JSON object with the following structure:
- `trip`: String describing the route and type (e.g., "FCO -> GIG GIG -> FCO (roundtrip)").
- `price_calendar`: A list of objects containing `OfferID`, `Flights` (outbound/return), `validatingCarrier`, `cabinType`, `passengers`, `totalPrice`, and `offerExpiresAt`.
- `metadata`: Information about the saved file path and origin.


## Configuration

The unit uses the following default parameters:
- `travel_dir`: Defaults to `mydata/travel`. This is where the resulting JSON files are stored.
