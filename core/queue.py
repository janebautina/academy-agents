"""Tasks agents hand to each other: queue.post("accountant", "Вернуть 2 990 ₽ покупателю X", "support").

The receiving agent takes its tasks with queue.take("accountant"). Every hand-over is in the journal.
"""
from __future__ import annotations

import uuid
from datetime import datetime, timezone

from core import data, journal

FILE = "queue.json"


def post(to: str, text: str, sender: str) -> str:
    items = data.load(FILE, [])
    item = {"id": uuid.uuid4().hex[:8], "to": to, "from": sender, "text": text,
            "at": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    items.append(item)
    data.save(FILE, items)
    journal.write(sender, f"передал задачу «{to}»: {text[:80]}")
    return item["id"]


def take(agent: str) -> list[dict]:
    items = data.load(FILE, [])
    mine = [it for it in items if it["to"] == agent]
    data.save(FILE, [it for it in items if it["to"] != agent])
    return mine


def peek() -> list[dict]:
    return data.load(FILE, [])
