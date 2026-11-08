"""Agent «Marketer»: a week of posts for the company's Telegram channel. Nothing goes out without the owner's «да».

    python3 -m agents.marketer.run             # publish the posts the owner approved; once a week, plan the week
    python3 -m agents.marketer.run --plan      # plan the week now, even if this week already has a plan
    python3 -m agents.marketer.run --dry-run   # only print what the model would receive
    python3 -m agents.marketer.run --status    # the content plan: what waits, what is approved, what is out
    python3 -m agents.marketer.run --now       # publish what the owner approved right now, without waiting for its day

Every draft comes to the owner in Telegram with «Да / Нет» buttons. «Да»: the post goes out on its
day to MARKETING_CHANNEL. «Нет»: it is dropped. Brand voice, topics and rules: company/marketing.md.
The director runs the marketer every 30 minutes, so an approved post is out within half an hour.
"""
from __future__ import annotations

import json
import sys
from datetime import date, timedelta
from pathlib import Path

from agents.director.run import now_local
from agents.secretary import sources
from core import approvals, data, env, journal, llm, telegram
from core.env import ROOT

HERE = Path(__file__).parent
FILE = "marketing.json"
DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
NAMES = ["пн", "вт", "ср", "чт", "пт", "сб", "вс"]
PLAN_HOUR = 10  # the week's plan comes on Monday (or the first run of the week) after 10:00


def week_of(day: date) -> str:
    year, week, _ = day.isocalendar()
    return f"{year}-W{week:02d}"


def plan_start(today: date) -> date:
    """The first day the plan covers: today on weekdays, next Monday at the weekend."""
    return today if today.weekday() < 5 else today + timedelta(days=7 - today.weekday())


def build_input(state: dict, today: date) -> str:
    charter = (ROOT / "company" / "COMPANY.md").read_text(encoding="utf-8")
    marketing = (ROOT / "company" / "marketing.md").read_text(encoding="utf-8")
    used = [p["topic"] for p in state["posts"] if p["status"] in ("published", "approved")][-20:]
    dropped = [p["topic"] for p in state["posts"] if p["status"] == "rejected"][-10:]
    return (
        f"Сегодня / Today: {today:%Y-%m-%d} ({DAYS[today.weekday()]})\n\n"
        f"=== УСТАВ / CHARTER ===\n{charter}\n\n"
        f"=== МАРКЕТИНГ / MARKETING ===\n{marketing}\n\n"
        f"=== ЗАДАЧИ / TASKS ===\n{sources.tasks()}\n\n"
        f"=== НОВОЕ В ЛЕНТАХ / FEEDS ===\n{sources.feeds(days=7)}\n\n"
        f"=== ЖУРНАЛ / JOURNAL ===\n{sources.recent_journal()}\n\n"
        f"=== ТЕМЫ, КОТОРЫЕ УЖЕ БЫЛИ / TOPICS ALREADY USED ===\n{chr(10).join(used) or '(пока нет)'}\n\n"
        f"=== ТЕМЫ, КОТОРЫЕ ВЛАДЕЛЕЦ ОТКЛОНИЛ / TOPICS THE OWNER REJECTED ===\n{chr(10).join(dropped) or '(пока нет)'}\n"
    )


def plan(state: dict, today: date) -> list[dict]:
    """Ask the model for the week, save the plan, send each post to the owner for «да»."""
    lang = env.get("COMPANY_LANGUAGE", "ru")
    answer = llm.chat((HERE / f"prompt.{lang}.md").read_text(encoding="utf-8"), build_input(state, today),
                      max_tokens=4000, json_mode=True)
    try:
        week = json.loads(answer)
    except json.JSONDecodeError:
        raise SystemExit("Нейросеть ответила не в формате JSON. Запустите ещё раз с --plan.")
    start = plan_start(today)
    monday = start - timedelta(days=start.weekday())
    new = []
    for p in week.get("posts", []):
        day = p.get("day") if p.get("day") in DAYS else DAYS[today.weekday()]
        on = max(monday + timedelta(days=DAYS.index(day)), start)  # a day already gone moves to today
        post = {"week": week_of(start), "date": on.isoformat(), "topic": p["topic"].strip(), "text": p["text"].strip(),
                "status": "waiting"}
        title = f"Пост на {NAMES[on.weekday()]} {on:%d.%m}: {post['topic']}"
        post["approval"] = approvals.ask("marketer", title, post["text"], {"date": post["date"]})
        state["posts"].append(post)
        new.append(post)
    state["week"] = week_of(start)
    data.save(FILE, state)
    report(week, new, start)
    journal.write("Маркетолог", f"план на неделю: постов {len(new)}, ждут «да» владельца")
    return new


def report(week: dict, posts: list[dict], today: date) -> None:
    """The plan as a file in reports/, and the short-video scripts to the owner (they are never published)."""
    lines = [f"# Контент-план {week_of(today)}", ""]
    lines += [f"## {NAMES[date.fromisoformat(p['date']).weekday()]} {p['date']} · {p['topic']}\n\n{p['text']}\n" for p in posts]
    shorts = week.get("shorts", [])
    if shorts:
        lines += ["# Шортсы (сценарии для владельца)", ""]
        lines += [f"## {s.get('title', '')}\n\n{s.get('script', '')}\n" for s in shorts]
    if week.get("note"):
        lines += ["# Заметка маркетолога", "", week["note"]]
    reports = ROOT / "reports"
    reports.mkdir(exist_ok=True)
    (reports / f"{week_of(today)}-marketer.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    if telegram.configured() and (shorts or week.get("note")):
        text = "**Маркетолог: план на неделю готов.** Посты пришли отдельно, с кнопками.\n"
        if week.get("note"):
            text += f"\n{week['note']}\n"
        for s in shorts:
            text += f"\n**Шортс: {s.get('title', '')}**\n{s.get('script', '')}\n"
        telegram.send(text)


def sync(state: dict) -> None:
    """Take the owner's answers from the approvals into the plan."""
    for post in state["posts"]:
        if post["status"] == "waiting":
            answer = approvals.status(post["approval"])
            if answer == "approved":
                post["status"] = "approved"
            elif answer == "rejected":
                post["status"] = "rejected"
                journal.write("Маркетолог", f"пост отклонён: {post['topic']}")


def publish(state: dict, today: date, any_day: bool = False) -> int:
    """Publish approved posts whose day has come (any_day: all approved ones). Returns how many went out."""
    due = [p for p in state["posts"] if p["status"] == "approved" and (any_day or p["date"] <= today.isoformat())]
    if not due:
        return 0
    channel = env.get("MARKETING_CHANNEL")
    if not channel:
        for p in due:
            if not p.get("warned"):
                p["warned"] = True
                msg = f"Пост «{p['topic']}» одобрен, но MARKETING_CHANNEL в .env пустой: некуда публиковать."
                print(msg)
                if telegram.configured():
                    telegram.send(msg)
        return 0
    for p in due:
        telegram.send(p["text"], chat_id=channel)
        p["status"], p["published_on"] = "published", today.isoformat()
        approvals.done(p["approval"])
        data.save(FILE, state)  # each post is marked right after it goes out: never twice
        journal.write("Маркетолог", f"опубликовал пост: {p['topic']}")
    return len(due)


def show(state: dict) -> None:
    marks = {"waiting": "ждёт «да»", "approved": "одобрен", "published": "опубликован", "rejected": "отклонён"}
    week = [p for p in state["posts"] if p["week"] == state.get("week")]
    print(f"Контент-план {state.get('week') or '—'}: постов {len(week)}")
    for p in week:
        print(f"  {NAMES[date.fromisoformat(p['date']).weekday()]} {p['date']}  {marks[p['status']]:<12} {p['topic']}")


def main() -> None:
    env.load()
    state = data.load(FILE, {"week": "", "posts": []})
    now = now_local()
    today = now.date()
    if "--dry-run" in sys.argv:
        print(build_input(state, today))
        return
    if "--status" in sys.argv:
        show(state)
        return
    sync(state)
    out = publish(state, today, any_day="--now" in sys.argv)
    planned = []
    if "--plan" in sys.argv or (state["week"] < week_of(plan_start(today)) and now.hour >= PLAN_HOUR):
        planned = plan(state, today)
    data.save(FILE, state)
    print(f"Опубликовано: {out}. Новых постов в плане: {len(planned)}.")
    if planned:
        show(state)


if __name__ == "__main__":
    main()
