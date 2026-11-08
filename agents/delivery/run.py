"""Agent «Delivery»: a course payment on DonationAlerts → a personal link to the private channel by email.

    python3 -m agents.delivery.run                  # one pass: new payments, joins (run every 15–30 min)
    python3 -m agents.delivery.run --dry-run        # show what it would do, send nothing
    python3 -m agents.delivery.run --revoke EMAIL   # refund: close the link and remove the buyer

Rules (from the charter): it delivers on its own only when the message has an email and the full
price. Anything else — no email, too little, a second payment — goes to the owner.
Each link lets in one person and expires in 7 days; the bot notes who joined with which link,
so a refund removes exactly that person.

.env: DA_ACCESS_TOKEN, TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (owner), COURSE_CHANNEL_RU,
      COURSE_CHANNEL_EN (optional), MAIL_FROM, RESEND_API_KEY, COURSE_PRICES (optional)
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

from agents.delivery import donations, letters
from core import env, journal, mailer, telegram
from core.env import ROOT


def state_path() -> Path:
    return Path(env.get("DELIVERY_STATE") or ROOT / "data" / "delivery.json")


def load() -> dict:
    p = state_path()
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}


def save(state: dict) -> None:
    p = state_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)


def masked(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}***@{domain}"


DRY = False


def owner(text: str) -> None:
    print(text)
    if telegram.configured() and not DRY:
        telegram.send(text)


def deliver(p: donations.Purchase, state: dict, dry: bool) -> None:
    buyers = state.setdefault("buyers", [])
    if not p.email:
        owner(f"Оплата курса без email: {p.name}, {p.amount:g} {p.currency} (донат {p.donation_id}). "
              f"Найдите покупателя и выдайте доступ вручную.")
        return
    if not p.paid_enough:
        owner(f"Донат с email, но сумма меньше цены курса: {p.name}, {p.amount:g} {p.currency}, {p.email}. Решите сами.")
        return
    channel = env.get(f"COURSE_CHANNEL_{p.lang.upper()}")
    if not channel:
        owner(f"Оплата курса ({p.lang}) от {p.email}, но канал COURSE_CHANNEL_{p.lang.upper()} не задан. Выдайте вручную.")
        return
    if any(b["email"] == p.email for b in buyers):
        owner(f"{p.email} платит за курс второй раз ({p.amount:g} {p.currency}). Отправляю новую ссылку; проверьте, не ошибка ли это.")
    if dry:
        print(f"[dry-run] ссылка и письмо для {p.email} ({p.lang})")
        return
    rec = next((b for b in buyers if b["donation_id"] == p.donation_id), None)
    if rec is None:  # the link is made once and kept, so a failed email is retried with the same link
        rec = {"donation_id": p.donation_id, "email": p.email, "lang": p.lang, "amount": p.amount,
               "currency": p.currency, "channel": channel, "link": telegram.invite_link(channel, f"donation {p.donation_id}"),
               "sent_at": None, "user_id": None, "revoked": False}
        buyers.append(rec)
        save(state)
    subject, text, html = letters.access(p.lang, rec["link"])
    mailer.send(p.email, subject, text, html, reply_to=env.get("MAIL_REPLY_TO", "support@aleshaai.com"))
    rec["sent_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    save(state)
    owner(f"Продажа: {p.amount:g} {p.currency} · {p.email} · письмо с доступом отправлено.")
    journal.write("Выдача доступа", f"доступ отправлен {masked(p.email)} ({p.amount:g} {p.currency})")


def new_payments(state: dict, dry: bool) -> int:
    since = datetime.fromisoformat(state["since"]).replace(tzinfo=None)
    seen = set(state.setdefault("seen", []))
    count = 0
    for d in sorted(donations.fetch(), key=lambda d: d["id"]):
        if d["id"] in seen or donations.created(d) < since:
            continue
        p = donations.parse(d)
        if p is not None:
            deliver(p, state, dry)
            count += 1
        unsent = any(b["donation_id"] == d["id"] and not b["sent_at"] for b in state.get("buyers", []))
        if not dry and not unsent:
            state["seen"].append(d["id"])
            save(state)
    return count


def track_joins(state: dict) -> None:
    """Who joined the channel with which link: needed to remove exactly that person on a refund."""
    answer = telegram.call("getUpdates", offset=state.get("offset", 0), allowed_updates=["chat_member"], timeout=0)
    by_name = {f"donation {b['donation_id']}": b for b in state.get("buyers", [])}
    for u in answer.get("result", []):
        state["offset"] = u["update_id"] + 1
        m = u.get("chat_member")
        if not m or m["new_chat_member"]["status"] != "member":
            continue
        user = m["new_chat_member"]["user"]
        buyer = by_name.get((m.get("invite_link") or {}).get("name", ""))
        if buyer:
            buyer["user_id"] = user["id"]
            journal.write("Выдача доступа", f"{masked(buyer['email'])} вошёл в канал")
        else:
            owner(f"В канал вошёл человек не по ссылке покупателя: {user.get('first_name', '')} (id {user['id']}). Проверьте.")
    save(state)


def revoke(email: str, state: dict) -> None:
    email = email.lower()
    found = [b for b in state.get("buyers", []) if b["email"] == email and not b["revoked"]]
    if not found:
        raise SystemExit(f"Покупателя {email} нет или доступ уже закрыт")
    for b in found:
        telegram.call("revokeChatInviteLink", chat_id=b["channel"], invite_link=b["link"])
        if b.get("user_id"):
            telegram.call("banChatMember", chat_id=b["channel"], user_id=b["user_id"])
        b["revoked"] = True
    save(state)
    owner(f"Доступ закрыт: {email} (ссылка отозвана{', человек удалён из канала' if any(b.get('user_id') for b in found) else ''}).")
    journal.write("Владелец", f"закрыл доступ {masked(email)} (возврат)")


def main() -> None:
    env.load()
    args = sys.argv[1:]
    state = load()
    if args[:1] == ["--revoke"] and len(args) == 2:
        revoke(args[1], state)
        return
    global DRY
    dry = DRY = "--dry-run" in args
    if "since" not in state:  # first run: only payments from now on, nothing old is re-sent
        state["since"] = datetime.now(timezone.utc).replace(tzinfo=None).isoformat(timespec="seconds")
        if not dry:
            save(state)
        owner("Выдача доступа запущена: беру оплаты курса с этой минуты.")
    n = new_payments(state, dry)
    if not dry:
        track_joins(state)
    print(f"Новых оплат курса: {n}")


if __name__ == "__main__":
    main()
