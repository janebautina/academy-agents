"""Delivery agent end to end: DonationAlerts, Telegram and email are faked at the network
boundary; everything else (parsing, rules, state, journal) is the real code.

    python3 -m unittest discover tests
"""
import io
import json
import os
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

from agents.delivery import donations
from agents.delivery import run as delivery
from core import journal, mailer, telegram


def donation(i, message, amount=2990, currency="RUB", minutes_ago=1, name="Иван"):
    t = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=minutes_ago)
    return {"id": i, "name": "donation", "username": name, "message_type": "text", "message": message,
            "amount": amount, "currency": currency, "is_shown": 1, "created_at": t.strftime("%Y-%m-%d %H.%M.%S")}


class ParseTest(unittest.TestCase):
    def test_course_payment_ru(self):
        p = donations.parse(donation(1, "КУРС ivan.petrov@yandex.ru"))
        self.assertEqual((p.email, p.lang, p.paid_enough), ("ivan.petrov@yandex.ru", "ru", True))

    def test_keyword_any_case_and_punctuation(self):
        self.assertIsNotNone(donations.parse(donation(1, "оплата за курс, почта: A.B@Mail.Ru.")))
        self.assertEqual(donations.parse(donation(1, "Курс: a.b@mail.ru.")).email, "a.b@mail.ru")

    def test_email_alone_is_a_purchase(self):
        p = donations.parse(donation(1, "maria.ivanova@gmail.com"))
        self.assertEqual((p.email, p.paid_enough), ("maria.ivanova@gmail.com", True))

    def test_course_payment_en(self):
        p = donations.parse(donation(1, "COURSE jane@example.com", amount=49, currency="USD"))
        self.assertEqual((p.lang, p.paid_enough), ("en", True))

    def test_stream_donation_is_not_a_purchase(self):
        self.assertIsNone(donations.parse(donation(1, "Привет! Классный стрим, спасибо")))
        self.assertIsNone(donations.parse(donation(1, "курсор завис, помогите")))

    def test_no_email_and_too_little(self):
        self.assertEqual(donations.parse(donation(1, "КУРС")).email, "")
        self.assertFalse(donations.parse(donation(1, "КУРС a@b.ru", amount=500)).paid_enough)
        self.assertFalse(donations.parse(donation(1, "COURSE a@b.ru", amount=49, currency="BTC")).paid_enough)


class FakeWorld:
    """Telegram + DonationAlerts + email, recorded instead of sent."""

    def __init__(self):
        self.calls, self.mails, self.donations, self.updates = [], [], [], []
        self.mail_fails = 0

    def tg(self, method, **params):
        self.calls.append((method, params))
        if method == "createChatInviteLink":
            n = sum(1 for m, _ in self.calls if m == "createChatInviteLink")
            return {"ok": True, "result": {"invite_link": f"https://t.me/+link{n}", "name": params["name"]}}
        if method == "getUpdates":
            ups, self.updates = self.updates, []
            return {"ok": True, "result": ups}
        return {"ok": True, "result": True}

    def mail(self, to, subject, text, html="", reply_to=""):
        if self.mail_fails:
            self.mail_fails -= 1
            raise mailer.MailError("Resend 500")
        self.mails.append((to, subject, text))
        return "id"

    def sent(self, method):
        return [p for m, p in self.calls if m == method]


class DeliveryTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        tmp = Path(self.tmp.name)
        self.state = tmp / "delivery.json"
        self.world = FakeWorld()
        env = {"DELIVERY_STATE": str(self.state), "DATA_DIR": str(tmp / "data"), "TELEGRAM_BOT_TOKEN": "x", "TELEGRAM_CHAT_ID": "1",
               "COURSE_CHANNEL_RU": "-100111", "MAIL_FROM": "Academy <support@aleshaai.com>", "DA_ACCESS_TOKEN": "t"}
        for p in [mock.patch.dict(os.environ, env), mock.patch.object(telegram, "_call", self.world.tg),
                  mock.patch.object(mailer, "send", self.world.mail), mock.patch.object(journal, "JOURNAL", tmp / "journal.md"),
                  mock.patch.object(donations, "fetch", lambda: list(self.world.donations)),
                  mock.patch.object(delivery.env, "load", lambda: None), mock.patch("sys.argv", ["run"]),
                  mock.patch("sys.stdout", io.StringIO())]:  # the agent prints for the owner; keep test output clean
            p.start()
            self.addCleanup(p.stop)
        delivery.main()  # first run: remembers "since", delivers nothing old
        self.world.calls.clear()

    def tearDown(self):
        self.tmp.cleanup()

    def owner_messages(self):
        return [p["text"] for p in self.world.sent("sendMessage")]

    def test_first_run_does_not_resend_old_payments(self):
        self.world.donations = [donation(1, "КУРС old@mail.ru", minutes_ago=60 * 24)]
        delivery.main()
        self.assertEqual(self.world.mails, [])

    def test_payment_gets_a_one_person_link_by_email(self):
        self.world.donations = [donation(10, "КУРС buyer@mail.ru", minutes_ago=-1)]
        delivery.main()
        link = self.world.sent("createChatInviteLink")
        self.assertEqual(len(link), 1)
        self.assertEqual((link[0]["chat_id"], link[0]["member_limit"]), ("-100111", 1))
        self.assertGreater(link[0]["expire_date"], datetime.now().timestamp() + 6 * 86400)
        to, subject, text = self.world.mails[0]
        self.assertEqual(to, "buyer@mail.ru")
        self.assertIn("https://t.me/+link1", text)
        self.assertIn("AI для бизнеса", subject)
        self.assertTrue(any("Продажа" in m for m in self.owner_messages()))
        self.assertIn("b***@mail.ru", journal.JOURNAL.read_text())
        self.assertNotIn("buyer@mail.ru", journal.JOURNAL.read_text())

    def test_second_run_sends_nothing_again(self):
        self.world.donations = [donation(10, "КУРС buyer@mail.ru", minutes_ago=-1)]
        delivery.main()
        delivery.main()
        self.assertEqual(len(self.world.mails), 1)
        self.assertEqual(len(self.world.sent("createChatInviteLink")), 1)

    def test_payment_with_only_an_email_is_delivered(self):
        self.world.donations = [donation(17, "Спасибо! anna@yandex.ru", minutes_ago=-1)]
        delivery.main()
        self.assertEqual(self.world.mails[0][0], "anna@yandex.ru")

    def test_small_donation_with_email_goes_to_the_owner(self):
        self.world.donations = [donation(18, "anna@yandex.ru", amount=100, minutes_ago=-1)]
        delivery.main()
        self.assertEqual(self.world.mails, [])
        self.assertTrue(any("меньше цены" in m for m in self.owner_messages()))

    def test_stream_donations_are_ignored(self):
        self.world.donations = [donation(11, "спасибо за стрим!", minutes_ago=-1)]
        delivery.main()
        self.assertEqual((self.world.mails, self.world.sent("createChatInviteLink")), ([], []))

    def test_missing_email_and_low_amount_go_to_the_owner(self):
        self.world.donations = [donation(12, "КУРС", minutes_ago=-1), donation(13, "КУРС x@y.ru", amount=300, minutes_ago=-1)]
        delivery.main()
        self.assertEqual(self.world.mails, [])
        msgs = " ".join(self.owner_messages())
        self.assertIn("без email", msgs)
        self.assertIn("меньше цены", msgs)

    def test_failed_email_is_retried_with_the_same_link(self):
        self.world.donations = [donation(14, "КУРС late@mail.ru", minutes_ago=-1)]
        self.world.mail_fails = 1
        with self.assertRaises(mailer.MailError):
            delivery.main()
        delivery.main()
        self.assertEqual(len(self.world.mails), 1)
        self.assertEqual(len(self.world.sent("createChatInviteLink")), 1)

    def test_join_is_tracked_and_refund_removes_that_person(self):
        self.world.donations = [donation(15, "КУРС refund@mail.ru", minutes_ago=-1)]
        delivery.main()
        self.world.updates = [{"update_id": 5, "chat_member": {
            "new_chat_member": {"status": "member", "user": {"id": 777, "first_name": "Ivan"}},
            "invite_link": {"invite_link": "https://t.me/+link1", "name": "donation 15"}}}]
        delivery.main()
        buyer = json.loads(self.state.read_text())["buyers"][0]
        self.assertEqual(buyer["user_id"], 777)
        with mock.patch("sys.argv", ["run", "--revoke", "refund@mail.ru"]):
            delivery.main()
        self.assertEqual(self.world.sent("revokeChatInviteLink")[0]["invite_link"], "https://t.me/+link1")
        self.assertEqual(self.world.sent("banChatMember")[0]["user_id"], 777)

    def test_refund_without_ban_right_asks_the_owner(self):
        self.world.donations = [donation(19, "КУРС noban@mail.ru", minutes_ago=-1)]
        delivery.main()
        self.world.updates = [{"update_id": 7, "chat_member": {
            "new_chat_member": {"status": "member", "user": {"id": 555, "first_name": "Petr"}},
            "invite_link": {"invite_link": "https://t.me/+link1", "name": "donation 19"}}}]
        delivery.main()
        real = self.world.tg

        def no_ban(method, **params):
            if method == "banChatMember":
                raise telegram.TelegramError("not enough rights")
            return real(method, **params)

        with mock.patch.object(telegram, "_call", no_ban), mock.patch("sys.argv", ["run", "--revoke", "noban@mail.ru"]):
            delivery.main()
        self.assertTrue(json.loads(self.state.read_text())["buyers"][0]["revoked"])
        self.assertTrue(any("555" in m for m in self.owner_messages()))

    def test_stranger_in_the_channel_is_reported(self):
        self.world.updates = [{"update_id": 6, "chat_member": {
            "new_chat_member": {"status": "member", "user": {"id": 999, "first_name": "Nobody"}}, "invite_link": None}}]
        delivery.main()
        self.assertTrue(any("не по ссылке покупателя" in m for m in self.owner_messages()))

    def test_dry_run_sends_nothing(self):
        self.world.donations = [donation(16, "КУРС dry@mail.ru", minutes_ago=-1)]
        with mock.patch("sys.argv", ["run", "--dry-run"]):
            delivery.main()
        self.assertEqual((self.world.mails, self.world.sent("createChatInviteLink"), self.world.sent("sendMessage")), ([], [], []))


if __name__ == "__main__":
    unittest.main()
