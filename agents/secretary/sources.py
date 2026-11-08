"""Everything the secretary reads before writing the morning summary.

- company/tasks.md: the owner's to-do list, one task per line;
- company/sources.txt: RSS feeds to watch (your YouTube channel, competitors, news);
- the company journal: what the agents did lately.
"""
from __future__ import annotations

import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone

from core import journal
from core.env import ROOT

NS = {"a": "http://www.w3.org/2005/Atom", "media": "http://search.yahoo.com/mrss/"}


def tasks() -> str:
    path = ROOT / "company" / "tasks.md"
    return path.read_text(encoding="utf-8") if path.exists() else "(файла задач нет)"


def feeds(days: int = 2) -> str:
    """New items of every feed in sources.txt from the last `days` days."""
    path = ROOT / "company" / "sources.txt"
    if not path.exists():
        return "(лент нет)"
    since = datetime.now(timezone.utc) - timedelta(days=days)
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        name, _, url = line.rpartition(" ")
        try:
            out += _read_feed(name or url, url, since)
        except Exception as e:  # one broken feed must not stop the summary
            out.append(f"[{name}] не удалось прочитать ленту: {e}")
    return "\n".join(out) or f"(за {days} дн. ничего нового)"


def _read_feed(name: str, url: str, since: datetime) -> list[str]:
    request = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0 academy-agents"})
    with urllib.request.urlopen(request, timeout=30) as response:
        root = ET.fromstring(response.read())
    items = []
    for entry in root.findall("a:entry", NS):  # Atom (YouTube and many blogs)
        published = datetime.fromisoformat(entry.findtext("a:published", "", NS).replace("Z", "+00:00"))
        views = entry.find(".//media:statistics", NS)
        stats = f", просмотров: {views.get('views')}" if views is not None else ""
        if published >= since:
            items.append(f"[{name}] {entry.findtext('a:title', '', NS)} ({published:%d.%m}{stats})")
    for item in root.iter("item"):  # RSS 2.0 (news sites, VK, Telegram via rss bridges)
        items.append(f"[{name}] {item.findtext('title', '')}")
    return items[:10]


def recent_journal() -> str:
    return journal.last(15)
