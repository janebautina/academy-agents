# academy-agents

A real one-person company run by AI agents: **Alesha AI Academy**.
Every "employee" here is an agent: it sells the course, delivers access, answers students,
counts the money and watches for outages. The owner approves anything risky.

Full program: [docs/ru/PROGRAM.md](docs/ru/PROGRAM.md).

This is the code of the paid course «AI для бизнеса: компания на AI-агентах» /
"AI for Your Business: the Agentic Company". Lessons (video + line-by-line walkthrough)
are in the course; the code is open.

| Lesson | Agent | Folder |
|---|---|---|
| 1 | Company charter + secretary (morning summary) | `agents/secretary/` · [урок / guide (RU)](docs/ru/lesson-01.md) |
| 2 | CTO (writes new agents into drafts/, owner approves) | `agents/cto/` · [урок / guide (RU)](docs/ru/lesson-02.md) |
| 3 | Marketer | — |
| 4 | Sales | — |
| 5 | Access delivery (DonationAlerts → one-person Telegram link by email) | `agents/delivery/` |
| 6 | Support | — |
| 7 | Accountant | — |
| 8 | On-call engineer | — |
| 9 | Director | — |
| 10 | Security and money | — |

## Model

All agents talk to an OpenAI-compatible API, so the model is one line in `.env`:
OpenAI, DeepSeek, YandexGPT (Yandex AI Studio) and others. Copy `.env.example` to `.env`
and fill in your own key. Never commit `.env`.

## Start your own company

1. **Use this template** › Private repository (your tasks and charter stay private).
2. Follow [docs/ru/lesson-01.md](docs/ru/lesson-01.md): Python, `.env`, your charter (`templates/COMPANY-template.md`), first run.
3. `python3 -m agents.secretary.run`

## Tests

`python3 -m unittest discover tests` — no packages to install. Telegram, DonationAlerts and email
are faked at the network boundary; the rest is the real code. CI runs them on Python 3.9 and 3.12.
