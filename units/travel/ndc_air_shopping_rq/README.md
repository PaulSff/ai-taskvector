# NdcAirShoppingRQ Unit

A TaskVector unit for sending NDC AirShopping XML requests to a remote API endpoint with built-in retry logic and authentication support.


## Overview

The `NdcAirShoppingRQ` unit is designed to facilitate the communication between the TaskVector framework and NDC-compliant airline APIs. It handles the transmission of XML payloads and captures the resulting XML responses or error messages.


## Interface

**Input Ports:**
- `xml_request` (str): The raw XML payload to be sent to the API.

**Output Ports:**
- `xml_response` (str): The XML response received from the server upon success.
- `error` (str): A description of the error if the request failed or the server returned a non-OK status.


## Configuration Parameters

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `url` | string | Required | The API endpoint URL |
| `username` | string | None | Basic Auth username |
| `password` | string | None | Basic Auth password |
| `timeout` | float | 30 | Request timeout in seconds |
| `retries` | int | 2 | Number of retry attempts on failure |
| `retry_delay` | float | 1.0 | Delay between retries in seconds |
| `headers` | dict | {} | Additional HTTP headers (Content-Type defaults to application/xml) |


## Implementation Details

The unit utilizes a `requests.Session` for efficiency. It includes a private helper `_send_request` that manages the retry loop and exception handling for `Timeout` and `RequestException`. The main step function `_ndc_air_shopping_rq_step` handles parameter validation and coercion before triggering the network call.
