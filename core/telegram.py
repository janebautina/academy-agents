"""Send a message to the owner in Telegram through the company bot.

Needs TELEGRAM_BOT_TOKEN (from @BotFather) and TELEGRAM_CHAT_ID in .env. Without
them the agents still work and print to the screen.

Find your chat id: write anything to your bot, then run
    python3 -m core.telegram
"""
from __future__ import annotations

import json
import urllib.parse
import urllib.request

from core import env

LIMIT = 4000  # Telegram allows 4096 characters per message


def configured() -> bool:
    return bool(env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"))


def _call(method: str, **params) -> dict:
    url = f"https://api.telegram.org/bot{env.need('TELEGRAM_BOT_TOKEN')}/{method}"
    data = urllib.parse.urlencode(params).encode()
    with urllib.request.urlopen(url, data=data, timeout=30) as response:
        return json.load(response)


def send(text: str) -> None:
    for start in range(0, len(text), LIMIT):
        _call("sendMessage", chat_id=env.need("TELEGRAM_CHAT_ID"), text=text[start:start + LIMIT])


if __name__ == "__main__":
    env.load()
    updates = _call("getUpdates").get("result", [])
    chats = {u["message"]["chat"]["id"]: u["message"]["chat"].get("first_name", "") for u in updates if "message" in u}
    if not chats:
        print("No messages yet. Write anything to your bot in Telegram and run this again.")
    for chat_id, name in chats.items():
        print(f"TELEGRAM_CHAT_ID={chat_id}   ({name})")
