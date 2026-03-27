from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Sequence


MAX_REPLY_BUTTONS = 3
MAX_INTERNAL_ID_CHARS = 120
MAX_BUTTON_TITLE_CHARS = 20
MAX_BUTTON_BODY_TEXT_CHARS = 1024
MAX_BUTTON_HEADER_CHARS = 20
MAX_BUTTON_FOOTER_CHARS = 60
MAX_LIST_ROWS_TOTAL = 10
MAX_LIST_SECTIONS = 10
MAX_LIST_BUTTON_TEXT_CHARS = 20
MAX_LIST_BODY_TEXT_CHARS = 4096
MAX_LIST_HEADER_CHARS = 60
MAX_LIST_FOOTER_CHARS = 60
MAX_LIST_SECTION_TITLE_CHARS = 24
MAX_LIST_ROW_TITLE_CHARS = 24
MAX_LIST_ROW_DESCRIPTION_CHARS = 72
MAX_LIST_ROW_ID_CHARS = MAX_INTERNAL_ID_CHARS


@dataclass(frozen=True)
class TextReply:
    text: str

    def to_dict(self) -> dict[str, Any]:
        return {"type": "text", "text": self.text}


@dataclass(frozen=True)
class Button:
    id: str
    title: str


@dataclass(frozen=True)
class ListRow:
    id: str
    title: str
    description: str | None = None


@dataclass(frozen=True)
class ListSection:
    title: str
    rows: Sequence[ListRow | Mapping[str, Any]]


def _required_non_empty_str(value: Any, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be a non-empty string")
    return value.strip()


def _validate_max_len(value: str, field_name: str, max_chars: int) -> str:
    if len(value) > max_chars:
        raise ValueError(f"{field_name} exceeds {max_chars} characters")
    return value


def _normalize_button(button: Button | Mapping[str, Any]) -> Button:
    if isinstance(button, Button):
        normalized = button
    elif isinstance(button, Mapping):
        normalized = Button(
            id=_required_non_empty_str(button.get("id"), "button.id"),
            title=_required_non_empty_str(button.get("title"), "button.title"),
        )
    else:
        raise ValueError("Each button must be a Button or mapping with id/title")

    _validate_max_len(normalized.id, "button.id", MAX_INTERNAL_ID_CHARS)
    _validate_max_len(normalized.title, "button.title", MAX_BUTTON_TITLE_CHARS)
    return normalized


def _normalize_list_row(row: ListRow | Mapping[str, Any]) -> ListRow:
    if isinstance(row, ListRow):
        normalized = row
    elif isinstance(row, Mapping):
        description_value = row.get("description")
        description: str | None
        if description_value is None:
            description = None
        elif isinstance(description_value, str):
            description = description_value.strip() or None
        else:
            raise ValueError("row.description must be a string when provided")

        normalized = ListRow(
            id=_required_non_empty_str(row.get("id"), "row.id"),
            title=_required_non_empty_str(row.get("title"), "row.title"),
            description=description,
        )
    else:
        raise ValueError("Each row must be a ListRow or mapping with id/title")

    _validate_max_len(normalized.id, "row.id", MAX_LIST_ROW_ID_CHARS)
    _validate_max_len(normalized.title, "row.title", MAX_LIST_ROW_TITLE_CHARS)
    if normalized.description is not None:
        _validate_max_len(normalized.description, "row.description", MAX_LIST_ROW_DESCRIPTION_CHARS)
    return normalized


def _normalize_list_section(section: ListSection | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(section, ListSection):
        title = _required_non_empty_str(section.title, "section.title")
        rows_input = section.rows
    elif isinstance(section, Mapping):
        title = _required_non_empty_str(section.get("title"), "section.title")
        rows_input = section.get("rows")
    else:
        raise ValueError("Each section must be a ListSection or mapping with title/rows")

    _validate_max_len(title, "section.title", MAX_LIST_SECTION_TITLE_CHARS)

    if not isinstance(rows_input, Sequence) or isinstance(rows_input, (str, bytes)) or not rows_input:
        raise ValueError("section.rows must contain at least 1 row")

    normalized_rows: list[dict[str, Any]] = []
    for row in rows_input:
        normalized_row = _normalize_list_row(row)
        row_payload: dict[str, Any] = {"id": normalized_row.id, "title": normalized_row.title}
        if normalized_row.description:
            row_payload["description"] = normalized_row.description
        normalized_rows.append(row_payload)

    return {"title": title, "rows": normalized_rows}


def create_message(user_id: str, text: str) -> dict[str, Any]:
    """Create a text message envelope for endpoint implementers.

    user_id is included for traceability/debugging by endpoint teams.
    """
    return {
        "user_id": _required_non_empty_str(user_id, "user_id"),
        "type": "text",
        "text": {"body": _required_non_empty_str(text, "text")},
    }


def create_buttoned_message(
    user_id: str,
    text: str,
    buttons: Sequence[Button | Mapping[str, Any]],
    *,
    header: str | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Create a WhatsApp interactive reply-buttons message envelope.

    buttons accepts up to 3 items, each with:
    - id: opaque value returned on click
    - title: button label (<= 20 chars)
    """
    normalized_user_id = _required_non_empty_str(user_id, "user_id")
    body_text = _required_non_empty_str(text, "text")
    _validate_max_len(body_text, "text", MAX_BUTTON_BODY_TEXT_CHARS)

    if not buttons:
        raise ValueError("buttons must contain at least 1 button")
    if len(buttons) > MAX_REPLY_BUTTONS:
        raise ValueError(f"WhatsApp supports up to {MAX_REPLY_BUTTONS} reply buttons")

    normalized_buttons = [_normalize_button(button) for button in buttons]

    interactive: dict[str, Any] = {
        "type": "button",
        "body": {"text": body_text},
        "action": {
            "buttons": [
                {
                    "type": "reply",
                    "reply": {"id": button.id, "title": button.title},
                }
                for button in normalized_buttons
            ]
        },
    }

    if header is not None:
        normalized_header = _required_non_empty_str(header, "header")
        _validate_max_len(normalized_header, "header", MAX_BUTTON_HEADER_CHARS)
        interactive["header"] = {
            "type": "text",
            "text": normalized_header,
        }
    if footer is not None:
        normalized_footer = _required_non_empty_str(footer, "footer")
        _validate_max_len(normalized_footer, "footer", MAX_BUTTON_FOOTER_CHARS)
        interactive["footer"] = {"text": normalized_footer}

    return {
        "user_id": normalized_user_id,
        "type": "interactive",
        "interactive": interactive,
    }


def create_list_message(
    user_id: str,
    text: str,
    button_text: str = "Options",
    sections: Sequence[ListSection | Mapping[str, Any]] | None = None,
    *,
    rows: Sequence[ListRow | Mapping[str, Any]] | None = None,
    section_title: str = "Options",
    header: str | None = None,
    footer: str | None = None,
) -> dict[str, Any]:
    """Create a WhatsApp interactive list message envelope.

    Simple mode:
    - provide rows (single-section list)

    Advanced mode:
    - provide sections directly

    Output shape mirrors Meta Cloud API interactive list syntax.
    """
    normalized_user_id = _required_non_empty_str(user_id, "user_id")
    body_text = _required_non_empty_str(text, "text")
    _validate_max_len(body_text, "text", MAX_LIST_BODY_TEXT_CHARS)
    normalized_button_text = _required_non_empty_str(button_text, "button_text")
    _validate_max_len(normalized_button_text, "button_text", MAX_LIST_BUTTON_TEXT_CHARS)

    if sections is not None and rows is not None:
        raise ValueError("Provide either sections or rows, not both")

    normalized_sections_input = sections
    if normalized_sections_input is None:
        if not rows:
            raise ValueError("rows must contain at least 1 row when sections is not provided")
        normalized_section_title = _required_non_empty_str(section_title, "section_title")
        _validate_max_len(normalized_section_title, "section_title", MAX_LIST_SECTION_TITLE_CHARS)
        normalized_sections_input = [{"title": normalized_section_title, "rows": list(rows)}]

    if len(normalized_sections_input) > MAX_LIST_SECTIONS:
        raise ValueError(f"WhatsApp supports up to {MAX_LIST_SECTIONS} sections in list messages")

    normalized_sections = [_normalize_list_section(section) for section in normalized_sections_input]
    total_rows = sum(len(section["rows"]) for section in normalized_sections)
    if total_rows > MAX_LIST_ROWS_TOTAL:
        raise ValueError(f"WhatsApp supports up to {MAX_LIST_ROWS_TOTAL} total rows in list messages")

    interactive: dict[str, Any] = {
        "type": "list",
        "body": {"text": body_text},
        "action": {
            "button": normalized_button_text,
            "sections": normalized_sections,
        },
    }

    if header is not None:
        normalized_header = _required_non_empty_str(header, "header")
        _validate_max_len(normalized_header, "header", MAX_LIST_HEADER_CHARS)
        interactive["header"] = {"type": "text", "text": normalized_header}
    if footer is not None:
        normalized_footer = _required_non_empty_str(footer, "footer")
        _validate_max_len(normalized_footer, "footer", MAX_LIST_FOOTER_CHARS)
        interactive["footer"] = {"text": normalized_footer}

    return create_interactive_message(user_id=normalized_user_id, interactive=interactive)


def create_location_request_message(user_id: str, text: str) -> dict[str, Any]:
    """Create a WhatsApp location request interactive message envelope."""
    normalized_user_id = _required_non_empty_str(user_id, "user_id")
    body_text = _required_non_empty_str(text, "text")
    _validate_max_len(body_text, "text", MAX_BUTTON_BODY_TEXT_CHARS)

    interactive: dict[str, Any] = {
        "type": "location_request_message",
        "body": {"text": body_text},
        "action": {"name": "send_location"},
    }
    return create_interactive_message(user_id=normalized_user_id, interactive=interactive)


def create_interactive_message(user_id: str, interactive: Mapping[str, Any]) -> dict[str, Any]:
    """Create an interactive message envelope for any interactive subtype."""
    normalized_user_id = _required_non_empty_str(user_id, "user_id")
    if not isinstance(interactive, Mapping):
        raise ValueError("interactive must be a mapping")
    interactive_type = interactive.get("type")
    if not isinstance(interactive_type, str) or not interactive_type.strip():
        raise ValueError("interactive.type must be a non-empty string")

    return {
        "user_id": normalized_user_id,
        "type": "interactive",
        "interactive": dict(interactive),
    }


def reply_text(text: str) -> dict[str, Any]:
    # Backward-compatible helper used by existing examples.
    return TextReply(text=text).to_dict()
