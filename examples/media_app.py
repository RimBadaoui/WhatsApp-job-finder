from __future__ import annotations

import requests

from wa_service_sdk import (
    AudioEvent,
    BaseEvent,
    Button,
    ImageEvent,
    InteractiveEvent,
    MediaDownloadError,
    MediaExpiredError,
    MediaTooLargeError,
    MediaUnavailableError,
    TextEvent,
    create_buttoned_message,
    create_message,
    download_media,
    media_uri_from_event,
    save_media_bytes,
)


def _run_image_logic(image_bytes: bytes) -> str:
    # Placeholder for OCR/classification/etc.
    return f"processed image bytes: {len(image_bytes)}"


def _run_voice_note_logic(audio_bytes: bytes) -> str:
    # Placeholder for transcription pipeline.
    return f"voice note bytes: {len(audio_bytes)}"


def _run_audio_logic(audio_bytes: bytes) -> str:
    # Placeholder for non-voice audio analysis.
    return f"audio bytes: {len(audio_bytes)}"


def _media_uri_or_unavailable(event: BaseEvent) -> str | None:
    media_uri = media_uri_from_event(event.raw)
    if media_uri:
        return media_uri
    return None


def _download_or_message(media_uri: str) -> tuple[bytes | None, str | None]:
    try:
        return download_media(media_uri), None
    except MediaExpiredError:
        return None, "Media link expired. Please resend the media."
    except MediaUnavailableError:
        return None, "Media unavailable. Please resend the media."
    except MediaTooLargeError:
        return None, "Media too large to process right now."
    except MediaDownloadError:
        return None, "Could not fetch media. Please try again."
    except requests.RequestException:
        return None, "Could not fetch media. Please try again."


def handle_image(event: ImageEvent) -> dict[str, object]:
    media_uri = _media_uri_or_unavailable(event)
    if not media_uri:
        return create_message(user_id=event.user_id, text="Media unavailable. Missing media.uri")

    image_bytes, error_text = _download_or_message(media_uri)
    if error_text:
        return create_message(user_id=event.user_id, text=error_text)
    assert image_bytes is not None

    saved_path = save_media_bytes(
        image_bytes,
        media_id=event.image_id,
        media_uri=media_uri,
        file_extension=event.file_extension,
        mime_type=event.mime_type,
    )
    image_result = _run_image_logic(image_bytes)
    caption_text = f" | caption: {event.caption}" if event.caption else ""
    return create_message(
        user_id=event.user_id,
        text=f"Received image ({event.image_id}){caption_text} | {image_result} | saved: {saved_path}",
    )


def handle_audio(event: AudioEvent) -> dict[str, object]:
    media_uri = _media_uri_or_unavailable(event)
    if not media_uri:
        return create_message(user_id=event.user_id, text="Media unavailable. Missing media.uri")

    audio_bytes, error_text = _download_or_message(media_uri)
    if error_text:
        return create_message(user_id=event.user_id, text=error_text)
    assert audio_bytes is not None

    saved_path = save_media_bytes(
        audio_bytes,
        media_id=event.audio_id,
        media_uri=media_uri,
        file_extension=event.file_extension,
        mime_type=event.mime_type,
    )
    if event.voice:
        audio_result = _run_voice_note_logic(audio_bytes)
        message = f"Received voice note ({event.audio_id}) | {audio_result} | saved: {saved_path}"
    else:
        audio_result = _run_audio_logic(audio_bytes)
        message = f"Received audio ({event.audio_id}) | {audio_result} | saved: {saved_path}"
    return create_message(user_id=event.user_id, text=message)


async def handle_event(event: BaseEvent):
    if isinstance(event, InteractiveEvent):
        return create_message(
            user_id=event.user_id,
            text=f"You clicked: {event.interaction_id}",
        )

    if isinstance(event, ImageEvent):
        return handle_image(event)

    if isinstance(event, AudioEvent):
        return handle_audio(event)

    if not isinstance(event, TextEvent):
        return create_message(user_id=event.user_id, text="Unsupported event")

    normalized = event.text.strip().lower()

    if normalized in {"hi", "hello"}:
        return create_buttoned_message(
            user_id=event.user_id,
            text="Hello! Pick an option:",
            buttons=[
                Button(id="help", title="Help"),
                Button(id="echo", title="Echo"),
                Button(id="option3", title="option3"),
            ],
        )

    return create_message(user_id=event.user_id, text=f"You said: {event.text}")
