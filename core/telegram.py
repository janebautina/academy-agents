"""Send a message to the owner in Telegram through the company bot.

Needs TELEGRAM_BOT_TOKEN (from @BotFather) and TELEGRAM_CHAT_ID in .env. Without
them the agents still work and print to the screen.

Find your chat id: write anything to your bot, then run
    python3 -m core.telegram
"""
from __future__ import annotations

import html
import json
import mimetypes
import re
import time
import urllib.error
import urllib.parse
import urllib.request
import uuid
from pathlib import Path

from core import env

LIMIT = 4000  # Telegram allows 4096 characters per message


def configured() -> bool:
    return bool(env.get("TELEGRAM_BOT_TOKEN") and env.get("TELEGRAM_CHAT_ID"))


class TelegramError(RuntimeError):
    pass


def _open(request: urllib.request.Request, timeout: int) -> dict:
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as e:
        answer = json.loads(e.read().decode() or "{}")
    if not answer.get("ok"):
        raise TelegramError(answer.get("description", "Telegram error"))
    return answer


def _call(method: str, **params) -> dict:
    """One Bot API call. Lists and dicts (keyboards, allowed_updates) are sent as JSON."""
    url = f"https://api.telegram.org/bot{env.need('TELEGRAM_BOT_TOKEN')}/{method}"
    flat = {k: json.dumps(v) if isinstance(v, (list, dict)) else v for k, v in params.items() if v is not None}
    return _open(urllib.request.Request(url, data=urllib.parse.urlencode(flat).encode()), timeout=60)


def call(method: str, **params) -> dict:
    return _call(method, **params)


def upload(method: str, field: str, path: Path, **params) -> dict:
    """Send a file (photo, video, document) with multipart/form-data. Bot API limit: 50 MB."""
    boundary = uuid.uuid4().hex
    body = b""
    for k, v in params.items():
        if v is None:
            continue
        v = json.dumps(v) if isinstance(v, (list, dict)) else str(v)
        body += f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n'.encode()
    kind = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body += (f'--{boundary}\r\nContent-Disposition: form-data; name="{field}"; filename="{path.name}"\r\n'
             f"Content-Type: {kind}\r\n\r\n").encode() + path.read_bytes() + f"\r\n--{boundary}--\r\n".encode()
    url = f"https://api.telegram.org/bot{env.need('TELEGRAM_BOT_TOKEN')}/{method}"
    request = urllib.request.Request(url, data=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
    return _open(request, timeout=600)


def invite_link(chat_id: str, name: str, days: int = 7) -> str:
    """A personal link into a private channel: one person, expires in `days`."""
    answer = _call("createChatInviteLink", chat_id=chat_id, name=name[:32], member_limit=1,
                   expire_date=int(time.time()) + days * 86400)
    return answer["result"]["invite_link"]


def to_html(text: str) -> str:
    """Models write **bold** (Markdown); Telegram shows it as bold only in its HTML mode."""
    text = html.escape(text, quote=False)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    return re.sub(r"^#+\s*(.+)$", r"<b>\1</b>", text, flags=re.M)


def send(text: str, chat_id: str = "") -> None:
    for start in range(0, len(text), LIMIT):
        part = to_html(text[start:start + LIMIT])
        _call("sendMessage", chat_id=chat_id or env.need("TELEGRAM_CHAT_ID"), text=part, parse_mode="HTML")


if __name__ == "__main__":
    env.load()
    updates = _call("getUpdates").get("result", [])
    chats = {u["message"]["chat"]["id"]: u["message"]["chat"].get("first_name", "") for u in updates if "message" in u}
    if not chats:
        print("No messages yet. Write anything to your bot in Telegram and run this again.")
    for chat_id, name in chats.items():
        print(f"TELEGRAM_CHAT_ID={chat_id}   ({name})")
