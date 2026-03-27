from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import Any

from .errors import EventValidationError, UnsupportedEventTypeError
from .models import AudioEvent, BaseEvent, ImageEvent, InteractiveEvent, LocationEvent, ReactionEvent, ReplyEvent, TextEvent

EventParser = Callable[[dict[str, Any]], BaseEvent]
HandlerResult = dict[str, Any] | None
Handler = Callable[[BaseEvent], HandlerResult | Awaitable[HandlerResult]]


def _required_str(data: dict[str, Any], key: str) -> str:
    value = data.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EventValidationError(f"Missing or invalid field: {key}")
    return value


def _optional_str(data: dict[str, Any], key: str) -> str | None:
    value = data.get(key)
    if value is None:
        return None
    if isinstance(value, str):
        stripped = value.strip()
        return stripped or None
    return None


def _optional_bool(data: dict[str, Any], key: str) -> bool | None:
    value = data.get(key)
    if isinstance(value, bool):
        return value
    return None


def _optional_int(data: dict[str, Any], key: str) -> int | None:
    value = data.get(key)
    if isinstance(value, int):
        return value
    return None


def _required_float(data: dict[str, Any], key: str) -> float:
    value = data.get(key)
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        stripped = value.strip()
        if not stripped:
            raise EventValidationError(f"Missing or invalid field: {key}")
        try:
            return float(stripped)
        except ValueError as exc:
            raise EventValidationError(f"Missing or invalid field: {key}") from exc
    raise EventValidationError(f"Missing or invalid field: {key}")


def parse_text_event(data: dict[str, Any]) -> TextEvent:
    text = _required_str(data, "text")

    return TextEvent(
        api_version=_required_str(data, "api_version"),
        event_id=_required_str(data, "event_id"),
        service=_required_str(data, "service"),
        type="text",
        timestamp=_required_str(data, "timestamp"),
        user_id=_required_str(data, "user_id"),
        raw=data,
        text=text,
    )


def parse_interactive_event(data: dict[str, Any]) -> InteractiveEvent:
    interactive = data.get("interactive")
    if not isinstance(interactive, dict):
        raise EventValidationError("Missing or invalid field: interactive")

    interactive_type = _required_str(interactive, "type")

    item = interactive.get(interactive_type)
    if not isinstance(item, dict):
        raise EventValidationError(f"Missing or invalid field: interactive.{interactive_type}")

    interaction_id = _required_str(item, "id")
    interaction_title = item.get("title")
    if interaction_title is not None and not isinstance(interaction_title, str):
        interaction_title = None

    return InteractiveEvent(
        api_version=_required_str(data, "api_version"),
        event_id=_required_str(data, "event_id"),
        service=_required_str(data, "service"),
        type="interactive",
        timestamp=_required_str(data, "timestamp"),
        user_id=_required_str(data, "user_id"),
        raw=data,
        interactive_type=interactive_type,
        interaction_id=interaction_id,
        interaction_title=interaction_title,
    )


def parse_image_event(data: dict[str, Any]) -> ImageEvent:
    media = data.get("media")
    legacy_image = data.get("image")
    if not isinstance(media, dict) and not isinstance(legacy_image, dict):
        raise EventValidationError("Missing or invalid field: media")

    if not isinstance(media, dict):
        media = {}

    media_type = _optional_str(media, "type")
    if media_type and media_type != "image":
        raise EventValidationError("Missing or invalid field: media.type")

    image_id = (
        _optional_str(media, "media_id")
        or _optional_str(media, "id")
        or (_required_str(legacy_image, "id") if isinstance(legacy_image, dict) else None)
    )
    if not image_id:
        raise EventValidationError("Missing or invalid field: media.media_id")

    mime_type = _optional_str(media, "mime_type")
    if mime_type is None and isinstance(legacy_image, dict):
        mime_type = _optional_str(legacy_image, "mime_type")

    caption = _optional_str(media, "caption")
    if caption is None and isinstance(legacy_image, dict):
        caption = _optional_str(legacy_image, "caption")

    sha256 = _optional_str(media, "sha256")
    if sha256 is None and isinstance(legacy_image, dict):
        sha256 = _optional_str(legacy_image, "sha256")

    return ImageEvent(
        api_version=_required_str(data, "api_version"),
        event_id=_required_str(data, "event_id"),
        service=_required_str(data, "service"),
        type="image",
        timestamp=_required_str(data, "timestamp"),
        user_id=_required_str(data, "user_id"),
        raw=data,
        image_id=image_id,
        media_uri=_optional_str(media, "uri"),
        file_extension=_optional_str(media, "file_extension"),
        mime_type=mime_type,
        caption=caption,
        sha256=sha256,
        expires_in_seconds=_optional_int(media, "expires_in_seconds"),
    )


def parse_audio_event(data: dict[str, Any]) -> AudioEvent:
    media = data.get("media")
    legacy_audio = data.get("audio")
    if not isinstance(media, dict) and not isinstance(legacy_audio, dict):
        raise EventValidationError("Missing or invalid field: media")

    if not isinstance(media, dict):
        media = {}

    media_type = _optional_str(media, "type")
    if media_type and media_type != "audio":
        raise EventValidationError("Missing or invalid field: media.type")

    audio_id = (
        _optional_str(media, "media_id")
        or _optional_str(media, "id")
        or (_required_str(legacy_audio, "id") if isinstance(legacy_audio, dict) else None)
    )
    if not audio_id:
        raise EventValidationError("Missing or invalid field: media.media_id")

    mime_type = _optional_str(media, "mime_type")
    if mime_type is None and isinstance(legacy_audio, dict):
        mime_type = _optional_str(legacy_audio, "mime_type")

    sha256 = _optional_str(media, "sha256")
    if sha256 is None and isinstance(legacy_audio, dict):
        sha256 = _optional_str(legacy_audio, "sha256")

    return AudioEvent(
        api_version=_required_str(data, "api_version"),
        event_id=_required_str(data, "event_id"),
        service=_required_str(data, "service"),
        type="audio",
        timestamp=_required_str(data, "timestamp"),
        user_id=_required_str(data, "user_id"),
        raw=data,
        audio_id=audio_id,
        media_uri=_optional_str(media, "uri"),
        file_extension=_optional_str(media, "file_extension"),
        mime_type=mime_type,
        voice=_optional_bool(media, "voice"),
        sha256=sha256,
        expires_in_seconds=_optional_int(media, "expires_in_seconds"),
    )


def parse_location_event(data: dict[str, Any]) -> LocationEvent:
    location = data.get("location")
    if isinstance(location, dict):
        latitude = _required_float(location, "latitude")
        longitude = _required_float(location, "longitude")
        name = _optional_str(location, "name")
        address = _optional_str(location, "address")
        url = _optional_str(location, "url")
    else:
        latitude = _required_float(data, "latitude")
        longitude = _required_float(data, "longitude")
        name = _optional_str(data, "name")
        address = _optional_str(data, "address")
        url = _optional_str(data, "url")

    return LocationEvent(
        api_version=_required_str(data, "api_version"),
        event_id=_required_str(data, "event_id"),
        service=_required_str(data, "service"),
        type="location",
        timestamp=_required_str(data, "timestamp"),
        user_id=_required_str(data, "user_id"),
        raw=data,
        latitude=latitude,
        longitude=longitude,
        name=name,
        address=address,
        url=url,
    )


def parse_reaction_event(data: dict[str, Any]) -> ReactionEvent:
    reaction = data.get("reaction")
    if not isinstance(reaction, dict):
        raise EventValidationError("Missing or invalid field: reaction")

    emoji = _required_str(reaction, "emoji")
    message_id = _optional_str(reaction, "message_id") or _optional_str(reaction, "messageId")
    message_text = (
        _optional_str(reaction, "message_text")
        or _optional_str(reaction, "message")
        or _optional_str(reaction, "text")
        or _optional_str(reaction, "body")
    )

    return ReactionEvent(
        api_version=_required_str(data, "api_version"),
        event_id=_required_str(data, "event_id"),
        service=_required_str(data, "service"),
        type="reaction",
        timestamp=_required_str(data, "timestamp"),
        user_id=_required_str(data, "user_id"),
        raw=data,
        emoji=emoji,
        message_id=message_id,
        message_text=message_text,
    )


def parse_reply_event(data: dict[str, Any]) -> ReplyEvent:
    text = _optional_str(data, "text")
    reply = data.get("reply")
    if text is None and isinstance(reply, dict):
        text = _optional_str(reply, "text") or _optional_str(reply, "body")
    if text is None:
        raise EventValidationError("Missing or invalid field: text")

    context = data.get("context")
    replied_to_message_id = (
        _optional_str(data, "reply_to_message_id")
        or (_optional_str(reply, "message_id") if isinstance(reply, dict) else None)
        or (_optional_str(reply, "id") if isinstance(reply, dict) else None)
        or (_optional_str(context, "id") if isinstance(context, dict) else None)
    )
    replied_to_text = (
        _optional_str(data, "reply_to_text")
        or (_optional_str(reply, "quoted_text") if isinstance(reply, dict) else None)
        or (_optional_str(reply, "message_text") if isinstance(reply, dict) else None)
        or (_optional_str(reply, "message") if isinstance(reply, dict) else None)
        or (_optional_str(context, "body") if isinstance(context, dict) else None)
        or (_optional_str(context, "text") if isinstance(context, dict) else None)
    )

    return ReplyEvent(
        api_version=_required_str(data, "api_version"),
        event_id=_required_str(data, "event_id"),
        service=_required_str(data, "service"),
        type="reply",
        timestamp=_required_str(data, "timestamp"),
        user_id=_required_str(data, "user_id"),
        raw=data,
        text=text,
        replied_to_message_id=replied_to_message_id,
        replied_to_text=replied_to_text,
    )


class EventRegistry:
    def __init__(self) -> None:
        self._parsers: dict[str, EventParser] = {}

    def register(self, event_type: str, parser: EventParser) -> None:
        self._parsers[event_type] = parser

    def parse(self, data: dict[str, Any]) -> BaseEvent:
        event_type = data.get("type")
        if not isinstance(event_type, str):
            raise EventValidationError("Missing or invalid field: type")

        parser = self._parsers.get(event_type)
        if parser is None:
            raise UnsupportedEventTypeError(f"Unsupported event type: {event_type}")
        return parser(data)


def default_registry() -> EventRegistry:
    registry = EventRegistry()
    registry.register("text", parse_text_event)
    registry.register("interactive", parse_interactive_event)
    registry.register("image", parse_image_event)
    registry.register("audio", parse_audio_event)
    registry.register("location", parse_location_event)
    registry.register("reaction", parse_reaction_event)
    registry.register("reply", parse_reply_event)
    return registry
