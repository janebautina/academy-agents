"""Agent «CTO»: writes the code of a new agent from the owner's plain-language request.

    python3 -m agents.cto.run "Сделай агента, который ..."   # writes a draft into drafts/<name>/
    python3 -m agents.cto.run --approve <name>               # owner's "yes": moves the draft into agents/

The draft is checked (Python syntax, allowed imports, files only inside its own folder) but
never run automatically: the owner reads it, tries it, and only then approves.
"""
from __future__ import annotations

import ast
import json
import shutil
import sys
from pathlib import Path

from core import env, journal, llm
from core.env import ROOT

HERE = Path(__file__).parent
DRAFTS = ROOT / "drafts"
ALLOWED = {"__future__", "core", "agents", "datetime", "json", "pathlib", "re", "sys", "time", "urllib",
           "xml", "html", "collections", "dataclasses", "typing", "textwrap", "random", "math", "csv"}
FORBIDDEN_CALLS = {"unlink", "rmdir", "rmtree", "remove", "system", "popen", "eval", "exec", "__import__"}


def context() -> str:
    parts = [f"=== УСТАВ ===\n{(ROOT / 'company' / 'COMPANY.md').read_text(encoding='utf-8')}"]
    for f in ["core/env.py", "core/llm.py", "core/telegram.py", "core/journal.py",
              "agents/secretary/run.py", "agents/secretary/sources.py"]:
        parts.append(f"=== {f} ===\n{(ROOT / f).read_text(encoding='utf-8')}")
    existing = sorted(p.name for p in (ROOT / "agents").iterdir() if p.is_dir() and not p.name.startswith("_"))
    parts.append("=== УЖЕ ЕСТЬ АГЕНТЫ ===\n" + ", ".join(existing))
    return "\n\n".join(parts)


def check(plan: dict) -> list[str]:
    """Problems that stop the draft from being saved. Empty list = ok."""
    problems = []
    name = plan.get("name", "")
    if not name.isidentifier() or (ROOT / "agents" / name).exists():
        problems.append(f"имя «{name}» не подходит или такой агент уже есть")
    for f in plan.get("files", []):
        path = Path(f["path"])
        if path.parts[:2] != ("agents", name) or ".." in path.parts:
            problems.append(f"файл {path} вне папки агента")
        if path.suffix == ".py":
            try:
                tree = ast.parse(f["content"])
            except SyntaxError as e:
                problems.append(f"{path}: ошибка в коде, строка {e.lineno}")
                continue
            for node in ast.walk(tree):
                mods = [a.name for a in node.names] if isinstance(node, ast.Import) else \
                       [node.module or ""] if isinstance(node, ast.ImportFrom) else []
                for m in mods:
                    if m.split(".")[0] not in ALLOWED:
                        problems.append(f"{path}: запрещённый модуль {m}")
                called = node.func.attr if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute) else \
                         node.func.id if isinstance(node, ast.Call) and isinstance(node.func, ast.Name) else ""
                if called in FORBIDDEN_CALLS:
                    problems.append(f"{path}: агенту нельзя {called}() — удалять файлы и запускать команды")
    if not any(f["path"].endswith("run.py") for f in plan.get("files", [])):
        problems.append("нет run.py")
    return problems


def draft(request: str) -> None:
    instructions = (HERE / "prompt.ru.md").read_text(encoding="utf-8")
    answer = llm.chat(instructions, f"{context()}\n\n=== ЗАДАЧА ВЛАДЕЛЬЦА ===\n{request}",
                      max_tokens=6000, json_mode=True)
    plan = json.loads(answer)
    problems = check(plan)
    if problems:
        print("Черновик не сохранён, технический директор ошибся:")
        print("\n".join(f"- {p}" for p in problems))
        journal.write("Технический директор", f"черновик «{request[:60]}» отклонён проверкой")
        return
    target = DRAFTS / plan["name"]
    if target.exists():
        shutil.rmtree(target)
    for f in plan["files"]:
        out = DRAFTS / Path(f["path"]).relative_to("agents")
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(f["content"], encoding="utf-8")
    (target / "__init__.py").touch()
    print(f"Черновик: {plan['title']}  →  drafts/{plan['name']}/\n")
    print(plan["summary"], "\n")
    for f in plan["files"]:
        print(f"  {f['path'].replace('agents/', 'drafts/', 1)}  ({f['content'].count(chr(10)) + 1} строк)")
    if plan.get("needs_owner_yes"):
        print("\nТолько с вашего «да»:", "; ".join(plan["needs_owner_yes"]))
    print(f"\nПопробовать черновик:  python3 -m drafts.{plan['name']}.run --dry-run")
    print(f"Принять в компанию:    python3 -m agents.cto.run --approve {plan['name']}")
    journal.write("Технический директор", f"написал черновик «{plan['title']}» (drafts/{plan['name']})")


def approve(name: str) -> None:
    src, dst = DRAFTS / name, ROOT / "agents" / name
    if not src.is_dir():
        raise SystemExit(f"Черновика drafts/{name} нет")
    if dst.exists():
        raise SystemExit(f"Агент agents/{name} уже есть — сначала уберите его сами")
    for py in src.rglob("*.py"):  # drafts run as drafts.<name>; in the company they run as agents.<name>
        py.write_text(py.read_text(encoding="utf-8").replace(f"drafts.{name}", f"agents.{name}"), encoding="utf-8")
    shutil.move(str(src), str(dst))
    print(f"Принят: agents/{name}/  ·  запуск: python3 -m agents.{name}.run")
    journal.write("Владелец", f"принял агента {name} в компанию")


def main() -> None:
    env.load()
    args = sys.argv[1:]
    if args[:1] == ["--approve"] and len(args) == 2:
        approve(args[1])
    elif args and not args[0].startswith("-"):
        draft(" ".join(args))
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
