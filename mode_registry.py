from __future__ import annotations

import json
import re
from typing import Any

import requests


MODE_RE = re.compile(r"^[A-Za-z0-9_-]{1,24}$")
REQUEST_TIMEOUT_SECONDS = 29
HTTP_TIMEOUT_SECONDS = 29


def _validate_mode_name(mode: str) -> None:
    if not isinstance(mode, str) or not MODE_RE.fullmatch(mode):
        raise ValueError(
            "mode must be 1-24 characters and contain only letters, numbers, underscores, and hyphens"
        )


def _request(
    method: str,
    path: str,
    api_key: str,
    base_url: str,
    payload: dict[str, Any] | None = None,
) -> dict[str, Any]:
    headers = {"x-api-key": api_key}
    if payload is not None:
        headers["content-type"] = "application/json"

    try:
        response = requests.request(
            method=method,
            url=f"{base_url.rstrip('/')}{path}",
            headers=headers,
            json=payload,
            timeout=REQUEST_TIMEOUT_SECONDS,
        )
    except requests.RequestException as exc:
        return {
            "ok": False,
            "status_code": 0,
            "error": f"Request failed: {exc}",
            "body": None,
            "raw_text": "",
        }

    try:
        body = response.json()
    except Exception:
        body = None

    return {
        "ok": 200 <= response.status_code < 300,
        "status_code": response.status_code,
        "error": None if 200 <= response.status_code < 300 else response.text,
        "body": body,
        "raw_text": response.text,
    }


def upsert_mode(
    mode: str,
    endpoint: str,
    api_key: str,
    base_url: str,
    enabled: bool = True,
    description: str | None = None,
) -> dict[str, Any]:
    _validate_mode_name(mode)

    payload: dict[str, Any] = {
        "target_type": "http",
        "endpoint": endpoint,
        "enabled": enabled,
        "http_method": "POST",
        "http_timeout_seconds": HTTP_TIMEOUT_SECONDS,
    }

    if description:
        payload["description"] = description

    return _request("PUT", f"/modes/{mode}", api_key=api_key, base_url=base_url, payload=payload)


def get_mode(mode: str, api_key: str, base_url: str) -> dict[str, Any]:
    _validate_mode_name(mode)
    return _request("GET", f"/modes/{mode}", api_key=api_key, base_url=base_url)


def list_modes(api_key: str, base_url: str, limit: int = 100) -> dict[str, Any]:
    limit = max(1, min(int(limit), 500))
    return _request("GET", f"/modes?limit={limit}", api_key=api_key, base_url=base_url)


def print_response(result: dict[str, Any]) -> None:
    print(f"HTTP {result['status_code']}")
    if result["body"] is not None:
        print(json.dumps(result["body"], indent=2))
        return
    print(result["raw_text"])
