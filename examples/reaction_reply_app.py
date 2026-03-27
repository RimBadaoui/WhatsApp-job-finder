from __future__ import annotations

from wa_service_sdk import BaseEvent, ReactionEvent, ReplyEvent, TextEvent, create_message


def _quoted_or_id(text: str | None, message_id: str | None) -> str:
    if text:
        return f'"{text}"'
    if message_id:
        return f"message id {message_id}"
    return "an earlier message"


async def handle_event(event: BaseEvent):
    if isinstance(event, ReactionEvent):
        target = _quoted_or_id(event.message_text, event.message_id)
        return create_message(
            user_id=event.user_id,
            text=f"You reacted {event.emoji} to {target}",
        )

    if isinstance(event, ReplyEvent):
        target = _quoted_or_id(event.replied_to_text, event.replied_to_message_id)
        return create_message(
            user_id=event.user_id,
            text=f'You replied "{event.text}" to {target}',
        )

    if isinstance(event, TextEvent):
        return create_message(
            user_id=event.user_id,
            text="Send a reply or reaction and I will summarize it with context.",
        )

    return create_message(user_id=event.user_id, text="Unsupported event type")
