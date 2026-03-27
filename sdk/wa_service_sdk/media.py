from __future__ import annotations

import logging
import mimetypes
import time
from pathlib import Path
from typing import Any
from urllib.parse import urlparse, urlsplit

import requests

from .errors import MediaDownloadError, MediaExpiredError, MediaTooLargeError, MediaUnavailableError

logger = logging.getLogger("wa_service_sdk")


def media_uri_from_event(raw_event: dict[str, Any]) -> str | None:
    media_obj = raw_event.get("media")
    if isinstance(media_obj, dict):
        media_uri = media_obj.get("uri")
        if isinstance(media_uri, str) and media_uri.strip():
            return media_uri.strip()
    return None


def _sanitize_uri_for_log(media_uri: str) -> str:
    parts = urlsplit(media_uri)
    return f"{parts.scheme}://{parts.netloc}{parts.path}"


def download_media(media_uri: str, *, timeout_seconds: int = 10, max_bytes: int = 10 * 1024 * 1024) -> bytes:
    parsed = urlparse(media_uri)
    if parsed.scheme.lower() != "https":
        raise MediaDownloadError("Only HTTPS media URLs are allowed")

    safe_uri = _sanitize_uri_for_log(media_uri)
    max_attempts = 2  # one bounded retry

    for attempt in range(1, max_attempts + 1):
        started_at = time.monotonic()
        try:
            with requests.get(media_uri, timeout=timeout_seconds, stream=True) as response:
                status = response.status_code
                if status in {401, 403}:
                    raise MediaExpiredError("Media URL expired or unauthorized")
                if status == 404:
                    raise MediaUnavailableError("Media not found")
                if 500 <= status <= 599:
                    if attempt < max_attempts:
                        continue
                    raise MediaDownloadError(f"Media server error: HTTP {status}")
                if status != 200:
                    raise MediaDownloadError(f"Media download failed: HTTP {status}")

                content_length = response.headers.get("content-length")
                if content_length and content_length.isdigit() and int(content_length) > max_bytes:
                    raise MediaTooLargeError("Media exceeds maximum allowed size")

                chunks: list[bytes] = []
                total = 0
                for chunk in response.iter_content(chunk_size=8192):
                    if not chunk:
                        continue
                    total += len(chunk)
                    if total > max_bytes:
                        raise MediaTooLargeError("Media exceeds maximum allowed size")
                    chunks.append(chunk)

                duration_ms = int((time.monotonic() - started_at) * 1000)
                logger.info(
                    "Media downloaded | uri=%s | bytes=%s | duration_ms=%s | attempt=%s",
                    safe_uri,
                    total,
                    duration_ms,
                    attempt,
                )
                return b"".join(chunks)
        except (MediaExpiredError, MediaTooLargeError, MediaUnavailableError):
            raise
        except requests.Timeout as exc:
            if attempt < max_attempts:
                continue
            raise MediaDownloadError("Media download timed out") from exc
        except requests.RequestException as exc:
            if attempt < max_attempts:
                continue
            raise MediaDownloadError("Media download failed") from exc
        finally:
            duration_ms = int((time.monotonic() - started_at) * 1000)
            logger.info(
                "Media download attempt finished | uri=%s | duration_ms=%s | attempt=%s",
                safe_uri,
                duration_ms,
                attempt,
            )

    raise MediaDownloadError("Media download failed after retry")


def download_media_bytes(media_uri: str, *, timeout_seconds: int = 10) -> bytes:
    # Backward-compatible alias.
    return download_media(media_uri, timeout_seconds=timeout_seconds)


def _suffix_from_mime_type(mime_type: str | None) -> str | None:
    if not mime_type:
        return None
    mime_type = mime_type.strip().lower()
    common = {
        "image/jpeg": ".jpg",
        "image/png": ".png",
        "image/webp": ".webp",
        "image/gif": ".gif",
        "image/heic": ".heic",
        "image/heif": ".heif",
    }
    if mime_type in common:
        return common[mime_type]
    guessed = mimetypes.guess_extension(mime_type)
    if guessed:
        return guessed
    return None


def save_media_bytes(
    media_bytes: bytes,
    *,
    media_id: str,
    media_uri: str | None = None,
    file_extension: str | None = None,
    mime_type: str | None = None,
    output_dir: str | Path = "tmp_downloads",
) -> Path:
    target_dir = Path(output_dir)
    target_dir.mkdir(parents=True, exist_ok=True)

    normalized_file_ext = None
    if file_extension:
        normalized_file_ext = file_extension.strip().lower().lstrip(".")
        if normalized_file_ext:
            normalized_file_ext = f".{normalized_file_ext}"

    suffix = normalized_file_ext or _suffix_from_mime_type(mime_type) or ".bin"
    if media_uri:
        parsed = urlparse(media_uri)
        uri_name = Path(parsed.path).name
        candidate_suffix = Path(uri_name).suffix
        if candidate_suffix and suffix == ".bin":
            suffix = candidate_suffix

    output_path = target_dir / f"{media_id}{suffix}"
    output_path.write_bytes(media_bytes)
    return output_path
