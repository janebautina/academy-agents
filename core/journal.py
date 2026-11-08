"""The company journal: one line per thing an agent did, so the owner can always check."""
from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from core.env import ROOT

# JOURNAL_FILE moves the journal next to the company's private data (e.g. in GitHub Actions)
JOURNAL = Path(os.environ.get("JOURNAL_FILE") or ROOT / "company" / "journal.md")


def write(agent: str, what: str) -> None:
    JOURNAL.parent.mkdir(exist_ok=True)
    if not JOURNAL.exists():
        JOURNAL.write_text("# Журнал компании / Company journal\n\n", encoding="utf-8")
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(f"- {datetime.now():%Y-%m-%d %H:%M} · {agent} · {what}\n")


def last(lines: int = 20) -> str:
    if not JOURNAL.exists():
        return "(журнал пуст)"
    return "\n".join(JOURNAL.read_text(encoding="utf-8").splitlines()[-lines:])
