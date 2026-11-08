"""Agent «Director»: runs the whole company. One command, one schedule for every agent.

    python3 -m agents.director.run              # one pass: owner's answers, then every agent whose time has come
    python3 -m agents.director.run --team       # who works when, and when each one last ran
    python3 -m agents.director.run --run NAME   # run one agent now

Run it every 15–30 minutes (cron, Task Scheduler or GitHub Actions) and the company works on its own.
The schedule is company/team.json (TEAM_FILE to use another one). An agent that fails does not stop
the others: the owner gets a message with the error.
"""
from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

from core import approvals, data, env, journal, queue, telegram
from core.env import ROOT

DAYS = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"]


def now_local() -> datetime:
    """Company time without time-zone files (they are missing on some Windows machines)."""
    return datetime.now(timezone.utc).replace(tzinfo=None) + timedelta(hours=float(env.get("COMPANY_UTC_OFFSET", "3")))


def team() -> list[dict]:
    path = Path(env.get("TEAM_FILE") or ROOT / "company" / "team.json")
    return json.loads(path.read_text(encoding="utf-8"))["agents"]


def due(when: str, last: datetime | None, now: datetime) -> bool:
    """Is it this agent's turn? `last` and `now` are company time."""
    parts = when.split()
    if parts[0] == "every":
        minutes = int(parts[1].rstrip("m"))
        return last is None or now - last >= timedelta(minutes=minutes) - timedelta(seconds=30)
    if parts[0] in ("daily", "weekly"):
        hh, mm = (int(x) for x in parts[-1].split(":"))
        slot = now.replace(hour=hh, minute=mm, second=0, microsecond=0)
        if parts[0] == "weekly":
            slot -= timedelta(days=(now.weekday() - DAYS.index(parts[1])) % 7)
        if now < slot:  # today's (this week's) slot has not come yet: look at the previous one
            slot -= timedelta(days=7 if parts[0] == "weekly" else 1)
        return (last is None or last < slot) and now - slot < timedelta(hours=12)  # do not catch up stale runs
    return False  # "manual"


def run_agent(name: str, timeout: int = 900) -> tuple[bool, str]:
    """Run agents/<name>/run.py in its own process, exactly as from the Terminal.
    A crash or a hang there cannot take the director or the other agents down."""
    try:
        done = subprocess.run([sys.executable, "-m", f"agents.{name}.run"], cwd=ROOT, capture_output=True,
                              text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return False, f"не закончил за {timeout // 60} мин"
    return done.returncode == 0, (done.stdout + ("\n" + done.stderr if done.returncode else "")).strip()


def tell_owner(text: str) -> None:
    print(text)
    if telegram.configured():
        telegram.send(text)


def one_pass() -> list[str]:
    answers = approvals.collect() if telegram.configured() else 0
    if answers:
        journal.write("Директор", f"получил ответов владельца: {answers}")
    state = data.load("director.json", {"last_run": {}})
    now = now_local()
    ran = []
    for a in team():
        last = state["last_run"].get(a["name"])
        if not due(a["when"], datetime.fromisoformat(last) if last else None, now):
            continue
        ok, output = run_agent(a["name"])
        state["last_run"][a["name"]] = now.isoformat(timespec="seconds")
        data.save("director.json", state)
        ran.append(a["name"])
        if not ok:
            tell_owner(f"Агент «{a['title']}» ({a['name']}) не справился:\n{output.strip()[-800:]}")
            journal.write("Директор", f"{a['title']}: ошибка")
    left = [t for t in queue.peek() if t["to"] not in {a["name"] for a in team()}]
    if left:
        tell_owner("В очереди задачи для сотрудников, которых нет в штате: " + ", ".join(sorted({t["to"] for t in left})))
    return ran


def show_team() -> None:
    state = data.load("director.json", {"last_run": {}})
    for a in team():
        print(f"{a['title']:<22} {a['name']:<16} {a['when']:<16} последний запуск: {state['last_run'].get(a['name'], '—')}")
    waiting = approvals.pending()
    print(f"\nЖдут вашего «да»: {len(waiting)}" + "".join(f"\n  · {w['agent']}: {w['title']}" for w in waiting))
    print(f"Задачи в очереди: {len(queue.peek())}")


def main() -> None:
    env.load()
    a = sys.argv[1:]
    if a[:1] == ["--team"]:
        show_team()
    elif a[:1] == ["--run"] and len(a) == 2:
        ok, output = run_agent(a[1])
        print(output)
        if not ok:
            raise SystemExit(1)
    else:
        ran = one_pass()
        print("Отработали: " + (", ".join(ran) if ran else "никто, ещё не время"))


if __name__ == "__main__":
    main()
