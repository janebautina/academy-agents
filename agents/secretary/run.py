"""Agent «Secretary»: every morning reads the company's data and sends the owner a summary.

    python3 -m agents.secretary.run            # write the summary, send to Telegram if set up
    python3 -m agents.secretary.run --dry-run  # only print what the model would receive
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from agents.secretary import sources
from core import env, journal, llm, telegram
from core.env import ROOT

HERE = Path(__file__).parent


def build_input() -> str:
    charter = (ROOT / "company" / "COMPANY.md").read_text(encoding="utf-8")
    return (
        f"Сегодня / Today: {date.today():%Y-%m-%d}\n\n"
        f"=== УСТАВ / CHARTER ===\n{charter}\n\n"
        f"=== ЗАДАЧИ / TASKS ===\n{sources.tasks()}\n\n"
        f"=== НОВОЕ В ЛЕНТАХ / FEEDS ===\n{sources.feeds()}\n\n"
        f"=== ЖУРНАЛ / JOURNAL ===\n{sources.recent_journal()}\n"
    )


def main() -> None:
    env.load()
    lang = env.get("COMPANY_LANGUAGE", "ru")
    instructions = (HERE / f"prompt.{lang}.md").read_text(encoding="utf-8")
    data = build_input()
    if "--dry-run" in sys.argv:
        print(data)
        return
    summary = llm.chat(instructions, data)
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    out = reports / f"{date.today():%Y-%m-%d}-secretary.md"
    out.write_text(summary + "\n", encoding="utf-8")
    print(summary)
    if telegram.configured():
        telegram.send(summary)
        where = "Telegram"
    else:
        where = str(out.relative_to(ROOT))
    journal.write("Секретарь", f"утренняя сводка › {where}")


if __name__ == "__main__":
    main()
