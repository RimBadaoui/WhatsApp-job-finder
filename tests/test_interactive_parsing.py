from __future__ import annotations

import sys
import unittest
from pathlib import Path

from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "sdk") not in sys.path:
    sys.path.insert(0, str(ROOT / "sdk"))

from wa_service_sdk.fastapi_adapter import create_app


class InteractiveParsingTests(unittest.TestCase):
    def test_interactive_list_reply_parses(self):
        seen: dict[str, str] = {}

        def _handler(event):
            seen["type"] = event.type
            seen["interactive_type"] = event.interactive_type
            seen["interaction_id"] = event.interaction_id
            return {"type": "text", "text": {"body": "ok"}, "user_id": event.user_id}

        app = create_app(_handler, path="/webhook")
        client = TestClient(app)
        response = client.post(
            "/webhook",
            json={
                "api_version": "2026-03-01",
                "event_id": "evt_1",
                "service": "newbot",
                "type": "interactive",
                "timestamp": "2026-03-03T10:00:00Z",
                "user_id": "u1",
                "interactive": {
                    "type": "list_reply",
                    "list_reply": {
                        "id": "plan_pro",
                        "title": "Pro",
                    },
                },
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(seen["type"], "interactive")
        self.assertEqual(seen["interactive_type"], "list_reply")
        self.assertEqual(seen["interaction_id"], "plan_pro")


if __name__ == "__main__":
    unittest.main()
