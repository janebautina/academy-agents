"""Marketer: the week's plan goes to the owner with buttons, only approved posts go out, on their day,
once. The model and Telegram are faked; the plan, approvals and publishing are the real code."""
import io
import json
import os
import shutil
import tempfile
import unittest
from datetime import date, datetime
from pathlib import Path
from unittest import mock

from agents.marketer import run as marketer
from core import approvals, data, journal, llm, telegram
from core.env import ROOT

WEEK = {"posts": [{"day": "mon", "topic": "Устав за 10 минут", "text": "Пост про устав"},
                  {"day": "wed", "topic": "Секретарь по утрам", "text": "Пост про секретаря"},
                  {"day": "fri", "topic": "Кнопка «да»", "text": "Пост про кнопку"}],
        "shorts": [{"title": "Агент не удалит файлы", "script": "Крючок. Суть. Призыв."}],
        "note": "План по темам 1–3."}
MONDAY = datetime.fromisoformat("2026-11-09T10:30")  # a Monday


class MarketerTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        (tmp / "company").mkdir()
        for name in ("COMPANY.md", "marketing.md", "tasks.md"):
            shutil.copy(ROOT / "company" / name, tmp / "company" / name)
        self.calls, self.inbox, self.prompts = [], [], []
        self.now = MONDAY
        for p in [mock.patch.dict(os.environ, {"DATA_DIR": str(tmp / "data"), "TELEGRAM_BOT_TOKEN": "x",
                                               "TELEGRAM_CHAT_ID": "100", "MARKETING_CHANNEL": "@academy_news"}),
                  mock.patch.object(telegram, "_call", self.tg), mock.patch.object(journal, "JOURNAL", tmp / "journal.md"),
                  mock.patch.object(marketer, "ROOT", tmp), mock.patch.object(marketer.sources, "ROOT", tmp),
                  mock.patch.object(marketer.sources, "feeds", lambda days=2: "(лент нет)"),
                  mock.patch.object(llm, "chat", self.model), mock.patch.object(marketer, "now_local", lambda: self.now),
                  mock.patch("sys.stdout", io.StringIO()), mock.patch("sys.argv", ["run"])]:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def model(self, system, user, **kw):
        self.prompts.append(user)
        return json.dumps(WEEK, ensure_ascii=False)

    def tg(self, method, **params):
        self.calls.append((method, params))
        if method == "getUpdates":
            ups, self.inbox = self.inbox, []
            return {"ok": True, "result": ups}
        return {"ok": True, "result": {"message_id": len(self.calls)}}

    def to_channel(self):
        return [p["text"] for m, p in self.calls if m == "sendMessage" and p["chat_id"] == "@academy_news"]

    def answer(self, topic, verdict):
        post = next(p for p in data.load(marketer.FILE, {})["posts"] if p["topic"] == topic)
        self.inbox.append({"update_id": len(self.calls) + 1000,
                           "callback_query": {"id": "q", "data": f"{verdict}:{post['approval']}", "from": {"id": 100}}})
        approvals.collect()

    def test_plan_asks_the_owner_and_publishes_nothing(self):
        marketer.main()
        posts = data.load(marketer.FILE, {})["posts"]
        self.assertEqual([p["status"] for p in posts], ["waiting"] * 3)
        self.assertEqual([p["date"] for p in posts], ["2026-11-09", "2026-11-11", "2026-11-13"])
        self.assertEqual(len(approvals.pending()), 3)
        self.assertEqual(self.to_channel(), [])
        self.assertTrue((Path(self.tmp.name) / "reports" / "2026-W46-marketer.md").exists())
        owner = [p["text"] for m, p in self.calls if m == "sendMessage" and p["chat_id"] == "100"]
        self.assertTrue(any("Агент не удалит файлы" in t for t in owner))  # the short's script goes to the owner only

    def test_approved_post_goes_out_on_its_day_once(self):
        marketer.main()
        self.answer("Секретарь по утрам", "yes")
        marketer.main()
        self.assertEqual(self.to_channel(), [])  # approved for Wednesday, today is Monday
        self.now = datetime.fromisoformat("2026-11-11T09:00")
        marketer.main()
        marketer.main()
        self.assertEqual(self.to_channel(), ["Пост про секретаря"])
        self.assertEqual(approvals.approved("marketer"), [])

    def test_rejected_post_never_goes_out_and_the_model_learns(self):
        marketer.main()
        self.answer("Устав за 10 минут", "no")
        marketer.main()
        self.assertEqual(self.to_channel(), [])
        self.now = datetime.fromisoformat("2026-11-16T10:30")  # next Monday: a new plan
        marketer.main()
        self.assertIn("Устав за 10 минут", self.prompts[-1].split("ОТКЛОНИЛ")[1])

    def test_one_plan_a_week_and_not_before_ten(self):
        self.now = datetime.fromisoformat("2026-11-09T08:00")
        marketer.main()
        self.assertEqual(self.prompts, [])
        self.now = MONDAY
        marketer.main()
        marketer.main()
        self.assertEqual(len(self.prompts), 1)

    def test_a_weekend_plan_is_for_next_week(self):
        self.now = datetime.fromisoformat("2026-11-08T12:00")  # Sunday
        with mock.patch("sys.argv", ["run", "--plan"]):
            marketer.main()
        state = data.load(marketer.FILE, {})
        self.assertEqual(state["week"], "2026-W46")
        self.assertEqual([p["date"] for p in state["posts"]], ["2026-11-09", "2026-11-11", "2026-11-13"])
        self.now = MONDAY
        marketer.main()
        self.assertEqual(len(self.prompts), 1)  # Monday does not plan the same week again

    def test_no_channel_warns_once(self):
        marketer.main()
        self.answer("Устав за 10 минут", "yes")
        with mock.patch.dict(os.environ, {"MARKETING_CHANNEL": ""}):
            marketer.main()
            marketer.main()
        warnings = [p["text"] for m, p in self.calls if m == "sendMessage" and "MARKETING_CHANNEL" in p["text"]]
        self.assertEqual(len(warnings), 1)
        self.assertEqual(data.load(marketer.FILE, {})["posts"][0]["status"], "approved")

    def test_bad_model_answer_saves_nothing(self):
        with mock.patch.object(llm, "chat", lambda *a, **k: "Вот ваш план: ..."):
            with self.assertRaises(SystemExit):
                marketer.main()
        self.assertEqual(approvals.pending(), [])


if __name__ == "__main__":
    unittest.main()
