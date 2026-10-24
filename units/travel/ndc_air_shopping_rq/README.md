# NdcAirShoppingRQ Unit

This unit is designed to send NDC (New Distribution Capability) AirShopping requests in XML format to a specified API endpoint. It includes robust error handling and a configurable retry mechanism to ensure reliability in travel industry integrations.

## Functionality

The unit takes an XML payload and transmits it via an HTTP POST request. It supports Basic Authentication and allows for fine-tuning of the network request parameters such as timeouts and retry intervals.

## Interface

### Input Ports
| Port | Type | Description |
| :--- | :--- | :--- |
| `xml_request` | `str` | The raw XML request body to be sent to the NDC endpoint. |

### Output Ports
| Port | Type | Description |
| :--- | :--- | :--- |
| `xml_response` | `str` | The XML response received from the server upon a successful request. |
| `error` | `str` | Error message if the request fails or if parameters are invalid. |

## Configuration Parameters

These parameters should be provided in the unit's `params` dictionary:

| Parameter | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `url` | `str` | (Required) | The target endpoint URL. |
| `username` | `str` | `None` | Username for Basic Authentication. |
| `password` | `str` | `None` | Password for Basic Authentication. |
| `timeout` | `float` | `30` | Request timeout in seconds. |
| `headers` | `dict` | `{}` | Additional HTTP headers. `Content-Type` and `Accept` default to `application/xml`. |
| `retries` | `int` | `2` | Number of retry attempts after an initial failure. |
| `retry_delay` | `float` | `1.0` | Delay between retries in seconds. |

## Implementation Details

- **Encoding**: The XML body is encoded as `utf-8` before transmission.
- **Retry Logic**: The unit catches `Timeout` and `RequestException` and retries the request up to the specified `retries` limit.
- **Validation**: The unit validates that the `url` is present and that numeric parameters (timeout, retries, delay) are correctly typed.

## Example Usage

**Input:**
`xml_request`: `<SITA:AirShoppingRQ>...</SITA:AirShoppingRQ>`

**Params:**
```json
{
  "url": "https://api.airline.com/ndc/shopping",
  "username": "my_user",
  "password": "my_pass",
  "retries": 3
}
```