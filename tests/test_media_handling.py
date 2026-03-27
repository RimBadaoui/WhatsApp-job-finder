from __future__ import annotations

import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "sdk") not in sys.path:
    sys.path.insert(0, str(ROOT / "sdk"))

import requests
from fastapi.testclient import TestClient

from examples.media_app import handle_audio, handle_image
from wa_service_sdk import AudioEvent, ImageEvent
from wa_service_sdk.fastapi_adapter import create_app
from wa_service_sdk.errors import (
    MediaDownloadError,
    MediaExpiredError,
    MediaTooLargeError,
)
from wa_service_sdk.media import download_media
from wa_service_sdk.media import save_media_bytes


class FakeResponse:
    def __init__(self, status_code: int, body: bytes, headers: dict[str, str] | None = None):
        self.status_code = status_code
        self._body = body
        self.headers = headers or {}

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def iter_content(self, chunk_size: int = 8192):
        for i in range(0, len(self._body), chunk_size):
            yield self._body[i : i + chunk_size]


class MediaAppTests(unittest.TestCase):
    def _base(self) -> dict[str, object]:
        return {
            "api_version": "2026-03-01",
            "event_id": "evt_1",
            "service": "newbot",
            "timestamp": "2026-03-03T10:00:00Z",
            "user_id": "u1",
        }

    @patch("examples.media_app.save_media_bytes", return_value=Path("tmp_downloads/img.jpg"))
    @patch("examples.media_app.download_media", return_value=b"abc")
    def test_image_without_caption(self, _download, _save):
        event = ImageEvent(
            **self._base(),
            type="image",
            raw={"media": {"uri": "https://example.com/x", "media_id": "m1", "type": "image"}},
            image_id="m1",
            media_uri="https://example.com/x",
            file_extension="jpg",
            mime_type="image/jpeg",
            caption=None,
            sha256=None,
            expires_in_seconds=None,
        )
        response = handle_image(event)
        self.assertIn("Received image", response["text"]["body"])
        self.assertNotIn("caption:", response["text"]["body"])

    @patch("examples.media_app.save_media_bytes", return_value=Path("tmp_downloads/img.jpg"))
    @patch("examples.media_app.download_media", return_value=b"abc")
    def test_image_with_caption(self, _download, _save):
        event = ImageEvent(
            **self._base(),
            type="image",
            raw={"media": {"uri": "https://example.com/x", "media_id": "m1", "type": "image"}},
            image_id="m1",
            media_uri="https://example.com/x",
            file_extension="jpg",
            mime_type="image/jpeg",
            caption="hello",
            sha256=None,
            expires_in_seconds=None,
        )
        response = handle_image(event)
        self.assertIn("caption: hello", response["text"]["body"])

    @patch("examples.media_app.save_media_bytes", return_value=Path("tmp_downloads/a.ogg"))
    @patch("examples.media_app.download_media", return_value=b"abc")
    def test_audio_voice_note(self, _download, _save):
        event = AudioEvent(
            **self._base(),
            type="audio",
            raw={"media": {"uri": "https://example.com/a", "media_id": "a1", "type": "audio", "voice": True}},
            audio_id="a1",
            media_uri="https://example.com/a",
            file_extension="ogg",
            mime_type="audio/ogg",
            voice=True,
            sha256=None,
            expires_in_seconds=None,
        )
        response = handle_audio(event)
        self.assertIn("Received voice note", response["text"]["body"])

    @patch("examples.media_app.save_media_bytes", return_value=Path("tmp_downloads/a.mp3"))
    @patch("examples.media_app.download_media", return_value=b"abc")
    def test_audio_non_voice(self, _download, _save):
        event = AudioEvent(
            **self._base(),
            type="audio",
            raw={"media": {"uri": "https://example.com/a", "media_id": "a1", "type": "audio", "voice": False}},
            audio_id="a1",
            media_uri="https://example.com/a",
            file_extension="mp3",
            mime_type="audio/mpeg",
            voice=False,
            sha256=None,
            expires_in_seconds=None,
        )
        response = handle_audio(event)
        self.assertIn("Received audio", response["text"]["body"])

    def test_missing_media_uri(self):
        event = ImageEvent(
            **self._base(),
            type="image",
            raw={"media": {"media_id": "m1", "type": "image"}},
            image_id="m1",
            media_uri=None,
            file_extension="jpg",
            mime_type="image/jpeg",
            caption=None,
            sha256=None,
            expires_in_seconds=None,
        )
        response = handle_image(event)
        self.assertIn("Media unavailable", response["text"]["body"])

    @patch("examples.media_app.download_media", side_effect=MediaExpiredError("expired"))
    def test_expired_media_uri(self, _download):
        event = ImageEvent(
            **self._base(),
            type="image",
            raw={"media": {"uri": "https://example.com/x", "media_id": "m1", "type": "image"}},
            image_id="m1",
            media_uri="https://example.com/x",
            file_extension="jpg",
            mime_type="image/jpeg",
            caption=None,
            sha256=None,
            expires_in_seconds=None,
        )
        response = handle_image(event)
        self.assertIn("expired", response["text"]["body"].lower())


class DownloadUtilityTests(unittest.TestCase):
    @patch("wa_service_sdk.media.requests.get")
    def test_reject_non_https(self, _get):
        with self.assertRaises(MediaDownloadError):
            download_media("http://example.com/x")

    @patch("wa_service_sdk.media.requests.get")
    def test_retry_on_transient_5xx(self, mock_get):
        mock_get.side_effect = [
            FakeResponse(503, b""),
            FakeResponse(200, b"hello", headers={"content-length": "5"}),
        ]
        data = download_media("https://example.com/x")
        self.assertEqual(data, b"hello")
        self.assertEqual(mock_get.call_count, 2)

    @patch("wa_service_sdk.media.requests.get")
    def test_timeout_path(self, mock_get):
        mock_get.side_effect = [requests.Timeout("t1"), requests.Timeout("t2")]
        with self.assertRaises(MediaDownloadError):
            download_media("https://example.com/x", timeout_seconds=1)

    @patch("wa_service_sdk.media.requests.get")
    def test_oversized_content_length(self, mock_get):
        mock_get.return_value = FakeResponse(200, b"abc", headers={"content-length": str(20 * 1024 * 1024)})
        with self.assertRaises(MediaTooLargeError):
            download_media("https://example.com/x", max_bytes=1024)

    def test_save_uses_file_extension_hint(self):
        output = save_media_bytes(
            b"abc",
            media_id="m1",
            file_extension="ogg",
            mime_type="audio/ogg",
            output_dir=ROOT / "tmp_downloads_test",
        )
        self.assertTrue(str(output).endswith(".ogg"))
        output.unlink(missing_ok=True)
        (ROOT / "tmp_downloads_test").rmdir()


class AdapterNormalizationTests(unittest.TestCase):
    def test_message_type_image_uses_media_contract(self):
        seen: dict[str, str] = {}

        def _handler(event):
            seen["type"] = event.type
            seen["user_id"] = event.user_id
            return {"type": "text", "text": {"body": "ok"}, "user_id": event.user_id}

        app = create_app(_handler, path="/webhook")
        client = TestClient(app)
        response = client.post(
            "/webhook",
            json={
                "message_type": "image",
                "mode": "newbot",
                "user_id": "u1",
                "media": {"type": "image", "media_id": "m1", "uri": "https://example.com/x"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["type"], "image")
        self.assertEqual(seen["user_id"], "u1")

    def test_message_type_audio_uses_media_contract(self):
        seen: dict[str, str] = {}

        def _handler(event):
            seen["type"] = event.type
            return {"type": "text", "text": {"body": "ok"}, "user_id": event.user_id}

        app = create_app(_handler, path="/webhook")
        client = TestClient(app)
        response = client.post(
            "/webhook",
            json={
                "message_type": "audio",
                "mode": "newbot",
                "user_id": "u1",
                "media": {"type": "audio", "media_id": "a1", "uri": "https://example.com/x", "voice": True},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["type"], "audio")

    def test_message_type_location_uses_location_contract(self):
        seen: dict[str, object] = {}

        def _handler(event):
            seen["type"] = event.type
            seen["lat"] = event.latitude
            seen["lon"] = event.longitude
            return {"type": "text", "text": {"body": "ok"}, "user_id": event.user_id}

        app = create_app(_handler, path="/webhook")
        client = TestClient(app)
        response = client.post(
            "/webhook",
            json={
                "message_type": "location",
                "mode": "newbot",
                "user_id": "u1",
                "location": {"latitude": 40.7128, "longitude": -74.0060},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["type"], "location")
        self.assertEqual(seen["lat"], 40.7128)
        self.assertEqual(seen["lon"], -74.0060)

    def test_message_type_reaction_uses_reaction_contract(self):
        seen: dict[str, object] = {}

        def _handler(event):
            seen["type"] = event.type
            seen["emoji"] = event.emoji
            return {"type": "text", "text": {"body": "ok"}, "user_id": event.user_id}

        app = create_app(_handler, path="/webhook")
        client = TestClient(app)
        response = client.post(
            "/webhook",
            json={
                "message_type": "reaction",
                "mode": "newbot",
                "user_id": "u1",
                "reaction": {"emoji": "👍", "message_id": "wamid.123"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["type"], "reaction")
        self.assertEqual(seen["emoji"], "👍")

    def test_message_type_reply_uses_reply_contract(self):
        seen: dict[str, object] = {}

        def _handler(event):
            seen["type"] = event.type
            seen["text"] = event.text
            seen["reply_id"] = event.replied_to_message_id
            seen["reply_text"] = event.replied_to_text
            return {"type": "text", "text": {"body": "ok"}, "user_id": event.user_id}

        app = create_app(_handler, path="/webhook")
        client = TestClient(app)
        response = client.post(
            "/webhook",
            json={
                "message_type": "reply",
                "mode": "newbot",
                "user_id": "u1",
                "text": {"body": "yes please"},
                "context": {"id": "wamid.orig", "body": "Pick one"},
            },
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["type"], "reply")
        self.assertEqual(seen["text"], "yes please")
        self.assertEqual(seen["reply_id"], "wamid.orig")
        self.assertEqual(seen["reply_text"], "Pick one")


if __name__ == "__main__":
    unittest.main()
