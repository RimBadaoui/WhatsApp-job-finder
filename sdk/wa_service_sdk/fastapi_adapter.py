from __future__ import annotations

import inspect
import json
import logging
import os
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request

from .core import Handler, default_registry
from .errors import EventValidationError, UnsupportedEventTypeError


def create_app(handler: Handler, *, path: str = "/events") -> FastAPI:
    app = FastAPI(title="WA Service SDK Endpoint")
    registry = default_registry()
    logger = logging.getLogger("wa_service_sdk")

    def _unwrap_payload(payload: dict[str, Any]) -> dict[str, Any]:
        # Common integration shape: {"body": {...}} or {"body": "{\"...\": ...}"}
        body = payload.get("body")
        if isinstance(body, dict):
            return body
        if isinstance(body, str):
            try:
                parsed = json.loads(body)
            except json.JSONDecodeError:
                return payload
            if isinstance(parsed, dict):
                return parsed
        return payload

    def _normalize_payload(payload: dict[str, Any]) -> dict[str, Any]:
        normalized = _unwrap_payload(payload)

        # Common orchestrator envelope:
        # {
        #   "version": "...",
        #   "user_id": "...",
        #   "mode": "...",
        #   "message_type": "...",
        #   "payload": {...actual message...}
        # }
        inner_payload = normalized.get("payload")
        if isinstance(inner_payload, dict):
            metadata = {k: v for k, v in normalized.items() if k != "payload"}
            normalized = {**inner_payload, **metadata}
        elif isinstance(normalized.get("message"), dict):
            message = normalized["message"]
            metadata = {k: v for k, v in normalized.items() if k != "message"}
            normalized = {**message, **metadata}

        # WhatsApp-style text shape: {"text": {"body": "..."}}
        text_obj = normalized.get("text")
        if isinstance(text_obj, dict):
            text_body = text_obj.get("body")
            if isinstance(text_body, str):
                normalized = {**normalized, "text": text_body}

        # If type is missing but message_type/text exists, infer type.
        if "type" not in normalized and isinstance(normalized.get("message_type"), str):
            normalized = {**normalized, "type": normalized["message_type"]}
        if "type" not in normalized and isinstance(normalized.get("text"), str):
            normalized = {**normalized, "type": "text"}
        if isinstance(normalized.get("message_type"), str):
            normalized = {**normalized, "type": normalized["message_type"]}

        event_type = normalized.get("type")

        # Fill common defaults for supported inbound event types.
        if event_type in {"text", "interactive", "image", "audio", "location", "reaction", "reply"}:
            normalized.setdefault("api_version", "2026-03-01")
            normalized.setdefault(
                "event_id",
                str(normalized.get("id") or normalized.get("message_id") or f"evt_{uuid4().hex}"),
            )
            normalized.setdefault(
                "service",
                str(normalized.get("mode") or os.getenv("DEFAULT_SERVICE", "default")),
            )
            normalized.setdefault(
                "timestamp",
                datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            )
            normalized.setdefault(
                "user_id",
                str(
                    normalized.get("user_id")
                    or normalized.get("userId")
                    or normalized.get("from")
                    or normalized.get("wa_id")
                    or "unknown-user"
                ),
            )

        return normalized

    def _payload_request_id(payload: dict[str, Any]) -> str | None:
        for key in ("request_id", "requestId", "x-request-id"):
            value = payload.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
        return None

    def _request_meta(payload: dict[str, Any]) -> tuple[str, str, str, str, str]:
        user_id = str(payload.get("user_id") or payload.get("from") or "unknown-user")
        mode = str(payload.get("mode") or payload.get("service") or "unknown-mode")
        message_type = str(payload.get("message_type") or payload.get("type") or "unknown")
        media_id = "n/a"
        media_obj = payload.get("media")
        if isinstance(media_obj, dict):
            media_id = str(media_obj.get("media_id") or media_obj.get("id") or "n/a")
        return user_id, mode, message_type, media_id, str(sorted(payload.keys()))

    @app.post(path)
    async def receive_event(request: Request) -> Any:
        try:
            payload = await request.json()
        except Exception as exc:  # noqa: BLE001
            raise HTTPException(status_code=400, detail="Invalid JSON payload") from exc

        if not isinstance(payload, dict):
            raise HTTPException(status_code=400, detail="Payload must be a JSON object")
        payload = _normalize_payload(payload)
        request_id = (
            request.headers.get("x-request-id")
            or request.headers.get("x-amzn-trace-id")
            or _payload_request_id(payload)
            or "n/a"
        )
        user_id, mode, message_type, media_id, payload_keys = _request_meta(payload)
        logger.info(
            "Webhook received | request_id=%s | user_id=%s | mode=%s | message_type=%s | media_id=%s",
            request_id,
            user_id,
            mode,
            message_type,
            media_id,
        )

        try:
            event = registry.parse(payload)
        except EventValidationError as exc:
            logger.warning(
                "Webhook validation error | request_id=%s | user_id=%s | mode=%s | message_type=%s | media_id=%s | error=%s | keys=%s",
                request_id,
                user_id,
                mode,
                message_type,
                media_id,
                str(exc),
                payload_keys,
            )
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except UnsupportedEventTypeError as exc:
            logger.warning(
                "Webhook unsupported type | request_id=%s | user_id=%s | mode=%s | message_type=%s | media_id=%s | error=%s | keys=%s",
                request_id,
                user_id,
                mode,
                message_type,
                media_id,
                str(exc),
                payload_keys,
            )
            raise HTTPException(status_code=422, detail=str(exc)) from exc
        logger.info(
            "Webhook parsed | request_id=%s | user_id=%s | mode=%s | message_type=%s | media_id=%s | type=%s",
            request_id,
            user_id,
            mode,
            message_type,
            media_id,
            event.type,
        )

        result = handler(event)
        if inspect.isawaitable(result):
            result = await result

        if result is None:
            return {}
        if not isinstance(result, dict):
            raise HTTPException(status_code=500, detail="Handler must return dict or None")
        return result

    @app.get("/health")
    async def health() -> dict[str, str]:
        return {"status": "ok"}

    return app
