from __future__ import annotations

from wa_service_sdk import (
    BaseEvent,
    Button,
    InteractiveEvent,
    ReactionEvent,
    TextEvent,
    create_buttoned_message,
    create_message,
)


async def handle_event(event: BaseEvent):
    if isinstance(event, ReactionEvent):
        return create_message(
            user_id=event.user_id,
            text=f"You reacted: {event.emoji}",
        )

    if isinstance(event, InteractiveEvent):
        return create_message(
            user_id=event.user_id,
            text=f"You clicked: {event.interaction_id}",
        )

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
