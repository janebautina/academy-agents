"""The owner's «да»: one place for every risky action of every agent.

An agent asks: approvals.ask("marketer", "Опубликовать пост", text, payload). The owner gets a
Telegram message with «Да / Нет» buttons. The director collects the answers on each run; the
agent sees approved requests with approvals.approved("marketer"), does the action and marks it
approvals.done(id). Only presses by the owner (TELEGRAM_CHAT_ID) count.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core import data, env, journal, telegram, updates

FILE = "approvals.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def ask(agent: str, title: str, details: str = "", payload: dict | None = None) -> str:
    items = data.load(FILE, [])
    for it in items:  # the same question is asked once
        if it["agent"] == agent and it["title"] == title and it["status"] == "pending":
            return it["id"]
    item = {"id": uuid.uuid4().hex[:8], "agent": agent, "title": title, "details": details,
            "payload": payload or {}, "status": "pending", "asked_at": _now(), "message_id": None}
    if telegram.configured():
        keyboard = {"inline_keyboard": [[{"text": "Да", "callback_data": f"yes:{item['id']}"},
                                         {"text": "Нет", "callback_data": f"no:{item['id']}"}]]}
        text = f"<b>Нужно ваше «да» · {telegram.html.escape(agent)}</b>\n{telegram.html.escape(title)}"
        if details:
            text += f"\n\n{telegram.html.escape(details[:3000])}"
        msg = telegram.call("sendMessage", chat_id=env.need("TELEGRAM_CHAT_ID"), text=text, parse_mode="HTML",
                            reply_markup=keyboard)
        item["message_id"] = msg["result"]["message_id"]
    items.append(item)
    data.save(FILE, items)
    journal.write(agent, f"просит «да»: {title}")
    return item["id"]


def collect() -> int:
    """Read the owner's button presses. Returns how many answers were recorded."""
    updates.fetch()
    items = data.load(FILE, [])
    by_id = {it["id"]: it for it in items}
    owner_id = str(env.get("TELEGRAM_CHAT_ID"))
    n = 0
    for u in updates.take("callback_query"):
        q = u["callback_query"]
        verdict, _, item_id = (q.get("data") or "").partition(":")
        it = by_id.get(item_id)
        if it is None or verdict not in ("yes", "no"):
            continue
        if str(q["from"]["id"]) != owner_id:  # someone else pressed: ignore
            try:
                telegram.call("answerCallbackQuery", callback_query_id=q["id"], text="Только владелец может решать")
            except telegram.TelegramError:
                pass
            continue
        if it["status"] == "pending":
            it["status"] = "approved" if verdict == "yes" else "rejected"
            it["answered_at"] = _now()
            n += 1
            journal.write("Владелец", f"{'да' if verdict == 'yes' else 'нет'}: {it['title']} ({it['agent']})")
        data.save(FILE, items)  # the owner's answer is saved before anything else can fail
        _acknowledge(q["id"], verdict, owner_id, it.get("message_id"))
    data.save(FILE, items)
    return n


def _acknowledge(query_id: str, verdict: str, chat_id: str, message_id) -> None:
    """Show the owner the answer was taken. Telegram refuses this for presses older than
    a few minutes (the director runs every 30), which must not lose the answer itself."""
    mark = "✓ Да" if verdict == "yes" else "✗ Нет"
    calls = [("answerCallbackQuery", {"callback_query_id": query_id, "text": mark})]
    if message_id:
        calls.append(("editMessageReplyMarkup", {"chat_id": chat_id, "message_id": message_id,
                                                  "reply_markup": {"inline_keyboard": [[{"text": mark, "callback_data": "noop"}]]}}))
    for method, params in calls:
        try:
            telegram.call(method, **params)
        except telegram.TelegramError:
            pass


def approved(agent: str) -> list[dict]:
    return [it for it in data.load(FILE, []) if it["agent"] == agent and it["status"] == "approved"]


def done(item_id: str) -> None:
    items = data.load(FILE, [])
    for it in items:
        if it["id"] == item_id:
            it["status"], it["done_at"] = "done", _now()
    data.save(FILE, items)


def status(item_id: str) -> str:
    """pending, approved, rejected or done; "" if there is no such request."""
    return next((it["status"] for it in data.load(FILE, []) if it["id"] == item_id), "")


def pending() -> list[dict]:
    return [it for it in data.load(FILE, []) if it["status"] == "pending"]
