from typing import TypedDict


class MessengerChat(TypedDict, total=False):
    id: str | int
    text: str
    sender: str
    timestamp: str
