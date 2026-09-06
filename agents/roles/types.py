"""Role configuration loaded from agents/roles/<role_id>/role.yaml.

The optional ``chat:`` block is represented directly on ``RoleConfig``.
There is intentionally no separate ``RoleChatConfig`` type.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from agents.tools.types import ToolList
from core.schemas.primitives import WorkflowInputs

type RoleIds = tuple[str, ...]


def _coerce_bool(value: Any, *, default: bool = False) -> bool:
    """Convert common YAML boolean representations to bool."""
    if value is None or value == "":
        return default

    if isinstance(value, str):
        return value.strip().lower() in {
            "1",
            "true",
            "yes",
            "y",
        }

    if isinstance(value, (bool, int, float)):
        return bool(value)

    return default


def _coerce_features(raw: Any) -> dict[str, bool]:
    """Convert a YAML feature mapping to ``dict[str, bool]``."""
    if raw is None or not isinstance(raw, dict):
        return {}

    features: dict[str, bool] = {}

    for key, value in raw.items():
        feature_name = str(key).strip()

        if not feature_name:
            continue

        if isinstance(value, bool):
            features[feature_name] = value
        elif isinstance(value, (int, float)):
            features[feature_name] = bool(value)
        elif isinstance(value, str):
            features[feature_name] = value.strip().lower() in {
                "1",
                "true",
                "yes",
                "y",
            }

    return features


def _parse_chat_fields(raw: Any) -> dict[str, Any]:
    """
    Parse the optional ``chat:`` YAML block.

    Supported forms:

    ```yaml
    chat: true
    ```

    ```yaml
    chat: false
    ```

    ```yaml
    chat:
      enabled: true
      workflow: workflow.json
      overrides:
        some_input: some_value
      features:
        attachments: true
      chat_handler: package.module:Handler
      analyst_mode: false
    ```
    """
    if raw is None:
        return {}

    if raw is True:
        return {
            "chat_enabled": True,
        }

    if raw is False:
        return {
            "chat_enabled": False,
        }

    if not isinstance(raw, dict):
        return {}

    workflow_raw = raw.get("workflow") or raw.get("chat_workflow")

    workflow: str | Path | None = (
        workflow_raw.strip()
        if isinstance(workflow_raw, str) and workflow_raw.strip()
        else None
    )

    raw_overrides = raw.get("overrides")

    if raw_overrides is not None and not isinstance(raw_overrides, dict):
        raise TypeError(
            "role.yaml field 'chat.overrides' must be a mapping or null"
        )

    handler_raw = raw.get("chat_handler") or raw.get("handler")

    chat_handler: str | None = (
        handler_raw.strip()
        if isinstance(handler_raw, str) and handler_raw.strip()
        else None
    )

    return {
        "chat_enabled": _coerce_bool(
            raw.get("enabled"),
            default=True,
        ),
        "chat_workflow": workflow,
        "chat_overrides": raw_overrides,
        "chat_features": _coerce_features(raw.get("features")),
        "chat_handler": chat_handler,
        "analyst_mode": _coerce_bool(raw.get("analyst_mode")),
    }


@dataclass(frozen=True)
class RoleConfig:
    """
    Agent persona, metadata, tools, follow-up settings, and chat configuration.

    ``follow_up_max_rounds`` being ``None`` means that application settings
    should be used.

    Chat configuration is read from the optional ``chat:`` block in
    ``role.yaml`` and is flattened onto this object.

    For example:

    ```yaml
    id: analyst
    role_name: Analyst
    name: Alex
    project_name: Example Project
    introduction_words: I analyze the available information.

    chat:
      enabled: true
      workflow: analyst_workflow.json
      overrides:
        temperature: 0.2
      features:
        attachments: true
      chat_handler: agents.roles.analyst:AnalystChatHandler
      analyst_mode: true
    ```
    """

    id: str
    role_name: str
    name: str
    project_name: str
    introduction_words: str

    responsibility_description: str = ""
    follow_up_max_rounds: int | None = None
    tools: ToolList = ()

    provider: str = ""
    ollama_host: str = ""
    ollama_model: str = ""

    # Flattened chat configuration.
    chat_enabled: bool = True
    chat_workflow: str | Path | None = None
    chat_overrides: WorkflowInputs | None = None
    chat_features: dict[str, bool] = field(default_factory=dict)
    chat_handler: str | None = None
    analyst_mode: bool = False

    extra: dict[str, object] = field(default_factory=dict)

    def chat_feature_enabled(
        self,
        key: str,
        *,
        default: bool = True,
    ) -> bool:
        """
        Read ``chat.features[key]``.

        If the feature is missing, ``default`` is returned.
        """
        return self.chat_features.get(key, default)


def parse_role_config(raw: Any) -> RoleConfig:
    """
    Parse a role configuration mapping.

    The input is normally the mapping loaded from ``role.yaml``.
    """
    if not isinstance(raw, dict):
        raise TypeError("role configuration must be a mapping")

    chat_fields = _parse_chat_fields(raw.get("chat"))

    raw_tools = raw.get("tools", ())
    if raw_tools is None:
        tools: ToolList = ()
    elif isinstance(raw_tools, (list, tuple)):
        tools = tuple(raw_tools)
    else:
        raise TypeError("role.yaml field 'tools' must be a list or tuple")

    raw_follow_up_max_rounds = raw.get("follow_up_max_rounds")

    if raw_follow_up_max_rounds is None:
        follow_up_max_rounds: int | None = None
    else:
        try:
            follow_up_max_rounds = int(raw_follow_up_max_rounds)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "role.yaml field 'follow_up_max_rounds' must be an integer or null"
            ) from exc

    raw_extra = raw.get("extra")

    if raw_extra is None:
        extra: dict[str, object] = {}
    elif isinstance(raw_extra, dict):
        extra = dict(raw_extra)
    else:
        raise TypeError("role.yaml field 'extra' must be a mapping or null")

    return RoleConfig(
        id=str(raw.get("id", "")),
        role_name=str(raw.get("role_name", "")),
        name=str(raw.get("name", "")),
        project_name=str(raw.get("project_name", "")),
        introduction_words=str(raw.get("introduction_words", "")),
        responsibility_description=str(
            raw.get("responsibility_description", "")
        ),
        follow_up_max_rounds=follow_up_max_rounds,
        tools=tools,
        provider=str(raw.get("provider", "")),
        ollama_host=str(raw.get("ollama_host", "")),
        ollama_model=str(raw.get("ollama_model", "")),
        extra=extra,
        **chat_fields,
    )
