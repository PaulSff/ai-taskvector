from typing import ClassVar, TypedDict

from pydantic import BaseModel, ConfigDict, Field


class MessengerChat(TypedDict, total=False):
    id: str | int
    text: str
    sender: str
    timestamp: str

class HistoryMessage(TypedDict, total=False):
    chat_id: str | int
    id: str | int
    text: str

class MessengerChatUpdate(BaseModel):
    model_config: ClassVar[ConfigDict] = ConfigDict(extra="ignore")

    chat_id: str | int
    unread_count: int
    chat: dict[str, object] = Field(default_factory=dict)
    messages: list[dict[str, object]] = Field(default_factory=list)
