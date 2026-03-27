from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class BaseEvent:
    api_version: str
    event_id: str
    service: str
    type: str
    timestamp: str
    user_id: str
    raw: dict[str, Any]


@dataclass(frozen=True)
class TextEvent(BaseEvent):
    text: str


@dataclass(frozen=True)
class InteractiveEvent(BaseEvent):
    interactive_type: str
    interaction_id: str
    interaction_title: str | None = None


@dataclass(frozen=True)
class ImageEvent(BaseEvent):
    image_id: str
    media_uri: str | None = None
    file_extension: str | None = None
    mime_type: str | None = None
    caption: str | None = None
    sha256: str | None = None
    expires_in_seconds: int | None = None


@dataclass(frozen=True)
class AudioEvent(BaseEvent):
    audio_id: str
    media_uri: str | None = None
    file_extension: str | None = None
    mime_type: str | None = None
    voice: bool | None = None
    sha256: str | None = None
    expires_in_seconds: int | None = None


@dataclass(frozen=True)
class LocationEvent(BaseEvent):
    latitude: float
    longitude: float
    name: str | None = None
    address: str | None = None
    url: str | None = None


@dataclass(frozen=True)
class ReactionEvent(BaseEvent):
    emoji: str
    message_id: str | None = None
    message_text: str | None = None


@dataclass(frozen=True)
class ReplyEvent(BaseEvent):
    text: str
    replied_to_message_id: str | None = None
    replied_to_text: str | None = None
