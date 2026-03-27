from __future__ import annotations

import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(ROOT / "sdk") not in sys.path:
    sys.path.insert(0, str(ROOT / "sdk"))

from wa_service_sdk.responses import (
    create_buttoned_message,
    create_interactive_message,
    create_list_message,
    create_location_request_message,
)


class ResponseValidationTests(unittest.TestCase):
    def test_button_id_max_120_chars(self):
        valid_id = "a" * 120
        payload = create_buttoned_message(
            user_id="u1",
            text="Choose one",
            buttons=[{"id": valid_id, "title": "Option"}],
        )
        reply_id = payload["interactive"]["action"]["buttons"][0]["reply"]["id"]
        self.assertEqual(reply_id, valid_id)

    def test_button_id_over_120_chars_rejected(self):
        too_long_id = "a" * 121
        with self.assertRaises(ValueError) as ctx:
            create_buttoned_message(
                user_id="u1",
                text="Choose one",
                buttons=[{"id": too_long_id, "title": "Option"}],
            )
        self.assertIn("button.id exceeds 120 characters", str(ctx.exception))

    def test_create_list_message_matches_meta_shape(self):
        payload = create_list_message(
            user_id="u1",
            text="Pick an option",
            button_text="Open menu",
            header="Header text",
            footer="Footer text",
            sections=[
                {
                    "title": "Main",
                    "rows": [
                        {"id": "r1", "title": "First", "description": "Desc 1"},
                        {"id": "r2", "title": "Second"},
                    ],
                }
            ],
        )
        self.assertEqual(payload["type"], "interactive")
        self.assertEqual(payload["interactive"]["type"], "list")
        self.assertEqual(payload["interactive"]["action"]["button"], "Open menu")
        self.assertEqual(payload["interactive"]["action"]["sections"][0]["rows"][0]["id"], "r1")

    def test_create_list_message_simple_rows_mode(self):
        payload = create_list_message(
            user_id="u1",
            text="Pick an option",
            rows=[
                {"id": "r1", "title": "First"},
                {"id": "r2", "title": "Second"},
            ],
        )
        self.assertEqual(payload["interactive"]["type"], "list")
        self.assertEqual(payload["interactive"]["action"]["button"], "Options")
        self.assertEqual(payload["interactive"]["action"]["sections"][0]["title"], "Options")
        self.assertEqual(len(payload["interactive"]["action"]["sections"][0]["rows"]), 2)

    def test_create_list_message_rejects_rows_and_sections_together(self):
        with self.assertRaises(ValueError) as ctx:
            create_list_message(
                user_id="u1",
                text="Pick an option",
                sections=[{"title": "Main", "rows": [{"id": "r1", "title": "First"}]}],
                rows=[{"id": "r2", "title": "Second"}],
            )
        self.assertIn("either sections or rows", str(ctx.exception))

    def test_list_row_id_over_120_chars_rejected(self):
        valid_id = "r" * 120
        payload = create_list_message(
            user_id="u1",
            text="Pick",
            button_text="Menu",
            sections=[{"title": "Main", "rows": [{"id": valid_id, "title": "Item"}]}],
        )
        self.assertEqual(payload["interactive"]["action"]["sections"][0]["rows"][0]["id"], valid_id)

        too_long_id = "r" * 121
        with self.assertRaises(ValueError) as ctx:
            create_list_message(
                user_id="u1",
                text="Pick",
                button_text="Menu",
                sections=[{"title": "Main", "rows": [{"id": too_long_id, "title": "Item"}]}],
            )
        self.assertIn("row.id exceeds 120 characters", str(ctx.exception))

    def test_button_footer_supported(self):
        payload = create_buttoned_message(
            user_id="u1",
            text="Pick one",
            buttons=[{"id": "b1", "title": "One"}],
            footer="Footer text",
        )
        self.assertEqual(payload["interactive"]["footer"]["text"], "Footer text")

    def test_list_limits_enforced(self):
        with self.assertRaises(ValueError):
            create_list_message(
                user_id="u1",
                text="x" * 4097,
                button_text="Menu",
                sections=[{"title": "Main", "rows": [{"id": "r1", "title": "Item"}]}],
            )

        with self.assertRaises(ValueError):
            create_list_message(
                user_id="u1",
                text="Pick",
                button_text="x" * 21,
                sections=[{"title": "Main", "rows": [{"id": "r1", "title": "Item"}]}],
            )

        with self.assertRaises(ValueError):
            create_list_message(
                user_id="u1",
                text="Pick",
                button_text="Menu",
                header="x" * 61,
                sections=[{"title": "Main", "rows": [{"id": "r1", "title": "Item"}]}],
            )

        with self.assertRaises(ValueError):
            create_list_message(
                user_id="u1",
                text="Pick",
                button_text="Menu",
                footer="x" * 61,
                sections=[{"title": "Main", "rows": [{"id": "r1", "title": "Item"}]}],
            )

    def test_create_interactive_message_passthrough(self):
        payload = create_interactive_message(
            user_id="u1",
            interactive={"type": "flow", "action": {"name": "flow_action", "parameters": {"flow_id": "f1"}}},
        )
        self.assertEqual(payload["type"], "interactive")
        self.assertEqual(payload["interactive"]["type"], "flow")

    def test_create_location_request_message(self):
        payload = create_location_request_message(user_id="u1", text="Please share your location")
        self.assertEqual(payload["type"], "interactive")
        self.assertEqual(payload["interactive"]["type"], "location_request_message")
        self.assertEqual(payload["interactive"]["action"]["name"], "send_location")
        self.assertEqual(payload["interactive"]["body"]["text"], "Please share your location")

    def test_create_location_request_message_body_limit(self):
        with self.assertRaises(ValueError) as ctx:
            create_location_request_message(user_id="u1", text="x" * 1025)
        self.assertIn("text exceeds 1024 characters", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
