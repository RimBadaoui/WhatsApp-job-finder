# WA Service SDK

Python SDK for parsing inbound WhatsApp events and building outbound response envelopes.

## Contents

- [1. Core Contract](#1-core-contract)
- [2. Inbound Event Types](#2-inbound-event-types)
- [3. Outbound Builders](#3-outbound-builders)
- [4. Limits](#4-limits)
- [5. Payload Shapes](#5-payload-shapes)
- [6. Unsupported Types](#6-unsupported-types)
- [7. Extension Strategy](#7-extension-strategy)

## 1. Core Contract

Your handler shape:

```python
async def handle_event(event: BaseEvent) -> dict | None:
    ...
```

`create_app(handle_event, path=...)` handles:

1. request parsing
2. normalization of common envelopes
3. typed event parsing
4. validation errors -> HTTP 400/422

## 2. Inbound Event Types

Registered parser types:

- `text` -> `TextEvent`
- `interactive` -> `InteractiveEvent`
- `reaction` -> `ReactionEvent`
- `reply` -> `ReplyEvent`
- `image` -> `ImageEvent`
- `audio` -> `AudioEvent`
- `location` -> `LocationEvent`

Common normalized defaults for supported types:

- `api_version`
- `event_id`
- `service`
- `timestamp`
- `user_id`

## 3. Outbound Builders

### Text

```python
create_message(user_id="u1", text="Hello")
```

### Reply buttons

```python
create_buttoned_message(
    user_id="u1",
    text="Pick one",
    buttons=[{"id": "help", "title": "Help"}],
    header=None,
    footer=None,
)
```

### List (simple mode)

```python
create_list_message(
    user_id="u1",
    text="Choose an option",
    rows=[{"id": "r1", "title": "Option 1"}],
)
```

### List (advanced mode)

```python
create_list_message(
    user_id="u1",
    text="Choose",
    button_text="Open",
    sections=[{"title": "Main", "rows": [{"id": "r1", "title": "Option 1"}]}],
    header="Header",
    footer="Footer",
)
```

### Location request

```python
create_location_request_message(
    user_id="u1",
    text="Share your location",
)
```

### Generic interactive

```python
create_interactive_message(
    user_id="u1",
    interactive={"type": "flow", "action": {"name": "flow_action"}},
)
```

## 4. Limits

### Button builder limits

- max 3 buttons
- button id max 120 chars
- button title max 20 chars
- body max 1024 chars
- header max 20 chars
- footer max 60 chars

### List builder limits

- max 10 sections
- max 10 total rows across sections
- row id max 120 chars
- row title max 24 chars
- row description max 72 chars
- section title max 24 chars
- button text max 20 chars
- body max 4096 chars
- header max 60 chars
- footer max 60 chars

### Location request limits

- body max 1024 chars

## 5. Payload Shapes

### Reaction input (supported)

```json
{
  "message_type": "reaction",
  "user_id": "u1",
  "reaction": {
    "emoji": "👍",
    "message_id": "wamid.123",
    "message_text": "Pick one"
  }
}
```

### Reply input (supported)

```json
{
  "message_type": "reply",
  "user_id": "u1",
  "text": {"body": "yes please"},
  "context": {"id": "wamid.orig", "body": "Pick one"}
}
```

### List output (Meta-style)

```json
{
  "user_id": "u1",
  "type": "interactive",
  "interactive": {
    "type": "list",
    "body": {"text": "Choose"},
    "action": {
      "button": "Open",
      "sections": [
        {"title": "Main", "rows": [{"id": "r1", "title": "Option 1"}]}
      ]
    }
  }
}
```

## 6. Unsupported Types

No first-class parser yet for:

- video
- document
- sticker
- contacts
- commerce/order payloads
- status/system events

## 7. Extension Strategy

To add a new inbound type:

1. Add event model in `models.py`
2. Add parser in `core.py`
3. Register parser in `default_registry()`
4. Add tests for adapter normalization + parser behavior

To add a new outbound type:

1. Add builder in `responses.py`
2. Add validation limits
3. Add tests for schema + limits
