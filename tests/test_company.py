"""The company as a whole: director's schedule, the owner's «да» buttons, the task queue,
the shared Telegram inbox, and a new hire joining the schedule. Telegram is faked."""
import io
import json
import os
import tempfile
import unittest
from datetime import datetime
from pathlib import Path
from unittest import mock

from agents.cto import run as cto
from agents.director import run as director
from core import approvals, journal, queue, telegram, updates


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.team = tmp / "team.json"
        self.team.write_text(json.dumps({"agents": [
            {"name": "secretary", "title": "Секретарь", "when": "daily 08:00"},
            {"name": "delivery", "title": "Выдача доступа", "when": "every 30m"},
            {"name": "cto", "title": "Технический директор", "when": "manual"}]}))
        self.calls, self.inbox = [], []
        for p in [mock.patch.dict(os.environ, {"DATA_DIR": str(tmp / "data"), "TEAM_FILE": str(self.team),
                                               "TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "100"}),
                  mock.patch.object(telegram, "_call", self.tg), mock.patch.object(journal, "JOURNAL", tmp / "journal.md"),
                  mock.patch("sys.stdout", io.StringIO())]:
            p.start()
            self.addCleanup(p.stop)

    def tearDown(self):
        self.tmp.cleanup()

    def tg(self, method, **params):
        self.calls.append((method, params))
        if method == "getUpdates":
            ups, self.inbox = self.inbox, []
            return {"ok": True, "result": ups}
        if method == "sendMessage":
            return {"ok": True, "result": {"message_id": len(self.calls)}}
        return {"ok": True, "result": True}

    def sent_texts(self):
        return [p["text"] for m, p in self.calls if m == "sendMessage"]


class ScheduleTest(unittest.TestCase):
    def t(self, s):
        return datetime.fromisoformat(s)

    def test_daily_runs_once_after_its_time(self):
        self.assertFalse(director.due("daily 08:00", None, self.t("2026-11-09T07:59")))
        self.assertTrue(director.due("daily 08:00", None, self.t("2026-11-09T08:05")))
        self.assertFalse(director.due("daily 08:00", self.t("2026-11-09T08:05"), self.t("2026-11-09T12:00")))
        self.assertTrue(director.due("daily 08:00", self.t("2026-11-09T08:05"), self.t("2026-11-10T08:01")))

    def test_daily_does_not_catch_up_a_stale_morning(self):
        self.assertFalse(director.due("daily 08:00", self.t("2026-11-08T08:00"), self.t("2026-11-09T23:00")))

    def test_every_and_manual(self):
        self.assertTrue(director.due("every 30m", self.t("2026-11-09T08:00"), self.t("2026-11-09T08:30")))
        self.assertFalse(director.due("every 30m", self.t("2026-11-09T08:00"), self.t("2026-11-09T08:10")))
        self.assertFalse(director.due("manual", None, self.t("2026-11-09T08:00")))

    def test_weekly(self):  # 2026-11-09 is a Monday
        self.assertTrue(director.due("weekly mon 09:00", None, self.t("2026-11-09T09:30")))
        self.assertFalse(director.due("weekly mon 09:00", self.t("2026-11-09T09:30"), self.t("2026-11-12T10:00")))


class DirectorTest(Base):
    def test_due_agents_run_and_a_failure_does_not_stop_the_others(self):
        ran = []

        def fake_run(name):
            ran.append(name)
            return (False, "Traceback: boom") if name == "secretary" else (True, "ok")

        with mock.patch.object(director, "run_agent", fake_run), \
             mock.patch.object(director, "now_local", lambda: datetime.fromisoformat("2026-11-09T08:10")):
            director.one_pass()
        self.assertEqual(ran, ["secretary", "delivery"])  # cto is manual
        self.assertTrue(any("не справился" in t and "boom" in t for t in self.sent_texts()))

    def test_second_pass_does_not_repeat_the_morning(self):
        ran = []
        with mock.patch.object(director, "run_agent", lambda n: ran.append(n) or (True, "")), \
             mock.patch.object(director, "now_local", lambda: datetime.fromisoformat("2026-11-09T08:10")):
            director.one_pass()
            director.one_pass()
        self.assertEqual(ran.count("secretary"), 1)

    def test_real_agent_module_is_run(self):
        ok, output = director.run_agent("cto")  # no arguments: prints its help and exits normally
        self.assertTrue(ok)
        self.assertIn("Технический директор", output)


class ApprovalsTest(Base):
    def press(self, data, user=100):
        self.inbox.append({"update_id": len(self.calls) + 1000,
                           "callback_query": {"id": "q1", "data": data, "from": {"id": user}}})

    def test_owner_yes_reaches_the_agent(self):
        item = approvals.ask("marketer", "Опубликовать пост", "текст поста")
        self.assertIn("inline_keyboard", json.dumps(dict(self.calls)["sendMessage"]["reply_markup"]))
        self.press(f"yes:{item}")
        approvals.collect()
        self.assertEqual([a["id"] for a in approvals.approved("marketer")], [item])
        approvals.done(item)
        self.assertEqual(approvals.approved("marketer"), [])

    def test_old_press_is_still_recorded(self):
        item = approvals.ask("director", "Тест")
        self.press(f"yes:{item}")
        real = self.tg

        def old_query(method, **params):
            if method == "answerCallbackQuery":
                raise telegram.TelegramError("Bad Request: query is too old")
            return real(method, **params)

        with mock.patch.object(telegram, "_call", old_query):
            approvals.collect()
        self.assertEqual([a["id"] for a in approvals.approved("director")], [item])

    def test_no_and_strangers(self):
        item = approvals.ask("support", "Вернуть деньги")
        self.press(f"yes:{item}", user=999)  # not the owner
        approvals.collect()
        self.assertEqual(approvals.approved("support"), [])
        self.press(f"no:{item}")
        approvals.collect()
        self.assertEqual(approvals.pending(), [])
        self.assertEqual(approvals.approved("support"), [])

    def test_same_question_is_asked_once(self):
        a = approvals.ask("marketer", "Опубликовать пост")
        b = approvals.ask("marketer", "Опубликовать пост")
        self.assertEqual(a, b)
        self.assertEqual(len(self.sent_texts()), 1)


class SharedInboxTest(Base):
    def test_each_agent_gets_its_own_kind_of_update(self):
        self.inbox = [{"update_id": 1, "callback_query": {"id": "q", "data": "x", "from": {"id": 100}}},
                      {"update_id": 2, "chat_member": {"new_chat_member": {"status": "member"}}}]
        updates.fetch()
        self.assertEqual(len(updates.take("callback_query")), 1)
        updates.fetch()  # nothing new from Telegram; the join is still waiting for delivery
        self.assertEqual(len(updates.take("chat_member")), 1)


class QueueTest(Base):
    def test_tasks_reach_only_their_agent(self):
        queue.post("accountant", "Вернуть 2 990 ₽ покупателю X", "support")
        queue.post("marketer", "Пост про новый урок", "director")
        self.assertEqual([t["text"] for t in queue.take("accountant")], ["Вернуть 2 990 ₽ покупателю X"])
        self.assertEqual(queue.take("accountant"), [])
        self.assertEqual(len(queue.peek()), 1)


class HireTest(Base):
    def test_approved_agent_joins_the_schedule(self):
        cto.hire("daily_report", "Итоги дня", "daily 21:00")
        cto.hire("daily_report", "Итоги дня", "daily 21:00")  # once
        names = [a["name"] for a in json.loads(self.team.read_text())["agents"]]
        self.assertEqual(names.count("daily_report"), 1)

    def test_odd_schedule_becomes_manual(self):
        self.assertEqual(cto.hire("x_agent", "X", "every evening"), "manual")


if __name__ == "__main__":
    unittest.main()
