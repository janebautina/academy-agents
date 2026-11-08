"""Read settings from the .env file next to the repository root.

Settings are lines like NAME=value. Real environment variables win, so the same
code runs on your laptop (reads .env) and in GitHub Actions (reads secrets).
"""
from __future__ import annotations

import os
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def load() -> None:
    env = ROOT / ".env"
    if not env.exists():
        return
    for line in env.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        os.environ.setdefault(name.strip(), value.strip())


def get(name: str, default: str = "") -> str:
    return os.environ.get(name, default).strip()


def need(name: str) -> str:
    value = get(name)
    if not value:
        raise SystemExit(f"{name} пустой: откройте файл .env и впишите значение (образец — .env.example).\n"
                         f"{name} is empty: open the .env file and fill it in (see .env.example).")
    return value
