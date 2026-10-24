# Air Shopping RQ Tool

## Overview

The `air_shopping_rq` tool allows the AI agent to request low-fare flight calendars via NDC (New Distribution Capability) protocols. It handles the transformation of structured JSON requests into the XML format required by the airline APIs and processes the XML responses back into a format suitable for the LLM's context.

## Architecture

### Data Flow
1. **Action Trigger**: The agent triggers the `get_low_fare_flight_calendar` action.
2. **Payload Injection**: The JSON payload is injected into the `air_shopping_rq` workflow.
3. **Transformation Pipeline**:
    - `NdcJsonToXml`: Converts the request payload to NDC-compliant XML.
    - `NdcAirShoppingRQ`: Performs the HTTP POST request to the airline API.
    - `NdcXmlToJson`: Parses the XML response back into JSON.
    - `Prompt`: Formats the final data into a system prompt for the agent.
4. **Follow-up**: The `run_air_shopping_rq_follow_up` function integrates this result back into the conversation context.

## Action Schema

### `get_low_fare_flight_calendar`

**Action Block Structure**:
```json
{
  "action": "get_low_fare_flight_calendar",
  "method": {
    "AirShoppingRQ": { ... request data ... }
  }
}
```

- **action**: Must be exactly `"get_low_fare_flight_calendar"`.
- **method.AirShoppingRQ**: Contains the specific NDC request parameters (e.g., origin, destination, dates).

## Technical Details

- **Timeout**: The tool has a default execution timeout of 30 seconds.
- **API Headers**: 
    - `Content-Type: application/xml`
    - `Accept: application/xml`
    - `PriceTTLMaxHours: 24`
- **Error Handling**: The tool includes robust error handling for validation errors, timeouts, and workflow crashes, providing toast notifications to the user via the `ExecutionFollowUpContext`.

## File Structure
- `__init__.py`: Contains the tool runner and follow-up logic.
- `action_block.py`: Defines the Pydantic schemas for action validation and registration.
- `air_shopping_rq.json`: The canonical workflow definition describing the unit graph and connections.