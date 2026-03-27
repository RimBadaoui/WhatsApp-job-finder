from __future__ import annotations

from wa_service_sdk import (
    BaseEvent,
    InteractiveEvent,
    LocationEvent,
    TextEvent,
    create_list_message,
    create_location_request_message,
    create_message,
)


def _nearby_bus_stops(latitude: float, longitude: float) -> list[dict[str, str]]:
    # Demo-only deterministic options, anchored around provided coordinates.
    return [
        {
            "id": f"stop_{abs(int(latitude * 1000)) % 100000}_1",
            "title": "Central Station",
            "description": "0.3 km | Route 24, 39",
        },
        {
            "id": f"stop_{abs(int(longitude * 1000)) % 100000}_2",
            "title": "Riverside Avenue",
            "description": "0.6 km | Route 11, 24",
        },
        {
            "id": f"stop_{(abs(int(latitude * longitude * 1000)) % 100000)}_3",
            "title": "City Hall",
            "description": "1.1 km | Route 39",
        },
    ]


def _location_label(event: LocationEvent) -> str:
    if event.name:
        return event.name
    if event.address:
        # Keep response short by using the first address segment.
        return event.address.split(",")[0].strip() or event.address
    return f"{event.latitude:.4f}, {event.longitude:.4f}"


async def handle_event(event: BaseEvent):
    if isinstance(event, LocationEvent):
        stops = _nearby_bus_stops(event.latitude, event.longitude)
        inferred_location = _location_label(event)
        return create_list_message(
            user_id=event.user_id,
            text=f"Here are bus stops near {inferred_location}. Pick one to get next departures.",
            button_text="View stops",
            section_title="Closest stops",
            rows=stops,
            footer="Live ETA integration coming next",
        )

    if isinstance(event, InteractiveEvent):
        if event.interactive_type == "list_reply":
            return create_message(
                user_id=event.user_id,
                text=f"Selected stop: {event.interaction_title or event.interaction_id}",
            )
        return create_message(user_id=event.user_id, text=f"Interaction received: {event.interaction_id}")

    if isinstance(event, TextEvent):
        normalized = event.text.strip().lower()
        if normalized in {"nearby bus", "bus", "bus stops", "nearby"}:
            return create_location_request_message(
                user_id=event.user_id,
                text="Share your location and I will show the nearest bus stops.",
            )
        return create_message(
            user_id=event.user_id,
            text="Send 'nearby bus' to find stops near you.",
        )

    return create_message(user_id=event.user_id, text="Unsupported event type")
