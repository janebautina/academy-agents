"""Where the company keeps its working state (approvals, queue, schedules, buyers).

DATA_DIR in .env or the environment; default: data/ next to the code. The folder is in
.gitignore: it holds personal data and must never go to a public repository.
"""
from __future__ import annotations

import json
from pathlib import Path

from core import env
from core.env import ROOT


def path(name: str) -> Path:
    return Path(env.get("DATA_DIR") or ROOT / "data") / name


def load(name: str, default):
    p = path(name)
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default


def save(name: str, value) -> None:
    p = path(name)
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(value, ensure_ascii=False, indent=1), encoding="utf-8")
    tmp.replace(p)
