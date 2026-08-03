"""HttpResponse unit. See README.md for interface."""
from units.canonical.http_response.http_response import (
    HTTP_RESPONSE_INPUT_PORTS,
    HTTP_RESPONSE_OUTPUT_PORTS,
    register_http_response,
)

__all__ = ["HTTP_RESPONSE_INPUT_PORTS", "HTTP_RESPONSE_OUTPUT_PORTS", "register_http_response"]
