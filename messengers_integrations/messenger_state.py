from typing import TypedDict

from pydantic import BaseModel, ConfigDict, Field


class MessengerChat(TypedDict, total=False):
    id: str | int
    text: str
    sender: str
    timestamp: str


class MessengerChatUpdate(BaseModel):
    model_config = ConfigDict(extra="ignore")

    chat_id: str | int
    unread_count: int
    chat: dict[str, object] = Field(default_factory=dict)
    messages: list[dict[str, object]] = Field(default_factory=list)
