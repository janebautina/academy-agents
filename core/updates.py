"""One shared inbox for everything Telegram sends to the company bot.

Telegram hands each update out once. Several agents need them (approvals need button
presses, delivery needs channel joins), so updates are fetched here once and kept in
data/telegram_updates.json until the agent that needs that kind takes them.
"""
from __future__ import annotations

from core import data, telegram

KINDS = ["message", "callback_query", "chat_member", "my_chat_member"]


def fetch() -> None:
    state = data.load("telegram_updates.json", {"offset": 0, "pending": []})
    answer = telegram.call("getUpdates", offset=state["offset"], allowed_updates=KINDS, timeout=0)
    for u in answer.get("result", []):
        state["offset"] = u["update_id"] + 1
        state["pending"].append(u)
    data.save("telegram_updates.json", state)


def take(kind: str) -> list[dict]:
    """Updates of one kind (e.g. "callback_query"), removed from the inbox."""
    state = data.load("telegram_updates.json", {"offset": 0, "pending": []})
    mine = [u for u in state["pending"] if kind in u]
    state["pending"] = [u for u in state["pending"] if kind not in u]
    data.save("telegram_updates.json", state)
    return mine
