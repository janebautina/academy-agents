"""Channel setup and posting: Telegram is faked, the rules are real."""
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from agents.delivery import channel
from core import telegram


class ChannelTest(unittest.TestCase):
    def setUp(self):
        self.calls = []
        self.rights = {"status": "administrator", **{r: True for r in channel.RIGHTS}}

        def tg(method, **params):
            self.calls.append((method, params))
            if method == "getMe":
                return {"ok": True, "result": {"id": 42}}
            if method == "getChatMember":
                return {"ok": True, "result": self.rights}
            if method == "sendMessage":
                return {"ok": True, "result": {"message_id": 7}}
            return {"ok": True, "result": True}

        self.uploads = []
        for p in [mock.patch.dict(os.environ, {"TELEGRAM_BOT_TOKEN": "x", "COURSE_CHANNEL_RU": "-100111"}),
                  mock.patch.object(telegram, "_call", tg),
                  mock.patch.object(telegram, "upload", lambda m, f, path, **kw: self.uploads.append((m, kw)))]:
            p.start()
            self.addCleanup(p.stop)

    def test_ready_bot_has_no_missing_rights(self):
        self.assertEqual(channel.check("ru"), [])

    def test_missing_invite_right_is_reported(self):
        self.rights["can_invite_users"] = False
        self.assertEqual(channel.check("ru"), ["can_invite_users"])

    def test_bot_that_is_not_admin_is_reported(self):
        self.rights = {"status": "member"}
        self.assertEqual(channel.check("ru"), ["бот не администратор канала"])

    def test_setup_pins_a_protected_welcome(self):
        channel.setup("ru", None)
        sent = dict(self.calls)["sendMessage"]
        self.assertTrue(sent["protect_content"])
        self.assertIn("Карта курса", sent["text"])
        self.assertEqual(dict(self.calls)["pinChatMessage"]["message_id"], 7)

    def test_lessons_are_posted_protected(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            f.write(b"0" * 1024)
            f.flush()
            channel.post("ru", Path(f.name), "Урок 1")
        method, kw = self.uploads[0]
        self.assertEqual(method, "sendVideo")
        self.assertTrue(kw["protect_content"])

    def test_too_big_video_is_refused(self):
        with tempfile.NamedTemporaryFile(suffix=".mp4") as f:
            f.truncate(51 * 1024 * 1024)
            with self.assertRaises(SystemExit):
                channel.post("ru", Path(f.name), "Урок")
        self.assertEqual(self.uploads, [])


if __name__ == "__main__":
    unittest.main()
