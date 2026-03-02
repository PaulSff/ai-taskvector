"""
IDAES-style import: map IDAES dict to canonical process graph dict.
Delegates to template with chemical as default environment_type.
"""
from typing import Any

from normalizer.template_import import to_canonical_dict as _template_to_canonical_dict


def to_canonical_dict(raw: dict[str, Any]) -> dict[str, Any]:
    """
    Map IDAES-style dict to canonical process graph dict.
    Accepts same shape as template: blocks/units, links/connections.
    Default environment_type is "chemical".
    """
    env_type = str(raw.get("environment_type", raw.get("process_environment_type", "chemical")))
    return _template_to_canonical_dict({**raw, "environment_type": env_type})
