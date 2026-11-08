"""Агент «Итоги дня»: вечером читает задачи и журнал за сегодня, пишет отчёт и отправляет в Telegram.

    python3 -m agents.daily_review.run            # создать отчёт и отправить в Telegram (если настроен)
    python3 -m agents.daily_review.run --dry-run  # только показать, что будет отправлено нейросети
"""
from __future__ import annotations

import sys
from datetime import date
from pathlib import Path

from core import env, journal, llm, telegram
from core.env import ROOT

HERE = Path(__file__).parent


def read_tasks() -> str:
    """Читает файл задач. Если файла нет — сообщает об этом."""
    path = ROOT / "company" / "tasks.md"
    if not path.exists():
        return "(файл задач не найден)"
    return path.read_text(encoding="utf-8")


def read_journal_today() -> str:
    """Берёт из журнала только строки за сегодняшнюю дату."""
    today = f"{date.today():%Y-%m-%d}"
    lines = []
    path = ROOT / "company" / "journal.md"
    if path.exists():
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.startswith(f"- {today}"):
                lines.append(line)
    return "\n".join(lines) if lines else "(сегодня в журнале нет записей)"


def build_input() -> str:
    """Собирает всё, что нужно нейросети для отчёта."""
    charter = (ROOT / "company" / "COMPANY.md").read_text(encoding="utf-8")
    return (
        f"Сегодня: {date.today():%Y-%m-%d}\n\n"
        f"=== УСТАВ ===\n{charter}\n\n"
        f"=== ЗАДАЧИ ===\n{read_tasks()}\n\n"
        f"=== ЖУРНАЛ ЗА СЕГОДНЯ ===\n{read_journal_today()}\n"
    )


def main() -> None:
    env.load()
    # Читаем инструкцию для нейросети
    instructions = (HERE / "prompt.ru.md").read_text(encoding="utf-8")
    data = build_input()

    # Режим проверки: только печатаем данные, нейросеть не вызываем
    if "--dry-run" in sys.argv:
        print(data)
        return

    # Просим нейросеть написать отчёт
    report = llm.chat(instructions, data)

    # Сохраняем отчёт в файл reports/ГГГГ-ММ-ДД-daily_review.md
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    out = reports / f"{date.today():%Y-%m-%d}-daily_review.md"
    out.write_text(report + "\n", encoding="utf-8")
    print(report)

    # Отправляем в Telegram, если настроен
    if telegram.configured():
        telegram.send(report)
        where = "Telegram"
    else:
        where = str(out.relative_to(ROOT))

    # Записываем в журнал, что сделали
    journal.write("Итоги дня", f"вечерний отчёт › {where}")


if __name__ == "__main__":
    main()
