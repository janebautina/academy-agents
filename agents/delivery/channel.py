"""Set up and fill the private course channel through the company bot.

    python3 -m agents.delivery.channel --check                    # is the bot an admin with the right rights?
    python3 -m agents.delivery.channel --setup ru --photo cover.jpg
    python3 -m agents.delivery.channel --post ru lesson.mp4 "Урок 1 · Устав и секретарь"
    python3 -m agents.delivery.channel --file ru template.xlsx "Шаблон устава"

Everything the bot posts is sent with protect_content: members cannot forward or save it.
Turn on «Restrict saving content» in the channel settings as well (Telegram app › channel ›
Edit › Channel type) — it also covers posts made by hand.
"""
from __future__ import annotations

import sys
from pathlib import Path

from core import env, telegram

TITLE = {"ru": "AI для бизнеса · компания на AI-агентах", "en": "AI for Business · the Agentic Company"}
DESCRIPTION = {
    "ru": "Закрытый канал курса Alesha AI Academy. Один владелец и команда AI-агентов: код, запуски, шаблоны. "
          "Вопросы: support@aleshaai.com",
    "en": "Private channel of the Alesha AI Academy course. One owner and a team of AI agents: code, runs, templates. "
          "Questions: support@aleshaai.com",
}
WELCOME = {
    "ru": """<b>Добро пожаловать в компанию из AI-агентов 👋</b>

Здесь вы шаг за шагом построите компанию, где сотрудников заменяют агенты, а вы принимаете решения.

<b>Как проходить курс</b>
1. Смотрите урок — идея и результат.
2. Повторяйте «Практику» — каждый клик на экране.
3. Запускайте у себя. Код: github.com/janebautina/academy-agents
4. Застряли — напишите номер шага и текст ошибки на support@aleshaai.com

<b>Карта курса</b>
1. Устав компании и секретарь
2. Технический директор
3. Маркетолог
4. Продавец
5. Выдача доступа
6. Поддержка
7. Бухгалтер
8. Дежурный инженер
9. Директор
10. Безопасность и деньги

Новые уроки появляются здесь же, без доплаты. Материалы канала защищены от пересылки — пожалуйста, не делитесь доступом.""",
    "en": """<b>Welcome to the agentic company 👋</b>

Step by step you'll build a company where agents do the work and you make the decisions.

<b>How to take the course</b>
1. Watch the lesson — the idea and the result.
2. Follow the Practice video — every click on screen.
3. Run it yourself. Code: github.com/janebautina/academy-agents
4. Stuck? Send the step number and the error text to support@aleshaai.com

<b>Course map</b>
1. Company charter and the secretary
2. CTO
3. Marketer
4. Sales
5. Access delivery
6. Support
7. Accountant
8. On-call engineer
9. Director
10. Security and money

New lessons arrive here at no extra cost. The channel is protected from forwarding — please don't share your access.""",
}
RIGHTS = ["can_invite_users", "can_post_messages", "can_edit_messages", "can_change_info", "can_restrict_members"]


def channel(lang: str) -> str:
    return env.need(f"COURSE_CHANNEL_{lang.upper()}")


def check(lang: str) -> list[str]:
    """Missing admin rights of the bot in the channel; empty list = ready."""
    me = telegram.call("getMe")["result"]["id"]
    member = telegram.call("getChatMember", chat_id=channel(lang), user_id=me)["result"]
    if member.get("status") != "administrator":
        return ["бот не администратор канала"]
    return [r for r in RIGHTS if not member.get(r)]


def setup(lang: str, photo: Path | None) -> None:
    chat = channel(lang)
    telegram.call("setChatTitle", chat_id=chat, title=TITLE[lang])
    telegram.call("setChatDescription", chat_id=chat, description=DESCRIPTION[lang])
    if photo:
        telegram.upload("setChatPhoto", "photo", photo, chat_id=chat)
    msg = telegram.call("sendMessage", chat_id=chat, text=WELCOME[lang], parse_mode="HTML",
                        protect_content=True, disable_web_page_preview=True)["result"]
    telegram.call("pinChatMessage", chat_id=chat, message_id=msg["message_id"], disable_notification=True)
    print(f"Канал оформлен: «{TITLE[lang]}», приветствие закреплено.")


def post(lang: str, video: Path, caption: str) -> None:
    if video.stat().st_size > 50 * 1024 * 1024:
        raise SystemExit("Видео больше 50 МБ — Bot API его не примет. Сожмите или загрузите вручную.")
    telegram.upload("sendVideo", "video", video, chat_id=channel(lang), caption=caption, parse_mode="HTML",
                    supports_streaming=True, protect_content=True)
    print(f"Опубликовано: {caption}")


def post_file(lang: str, path: Path, caption: str) -> None:
    telegram.upload("sendDocument", "document", path, chat_id=channel(lang), caption=caption, protect_content=True)
    print(f"Файл опубликован: {caption}")


def main() -> None:
    env.load()
    a = sys.argv[1:]
    if a[:1] == ["--check"]:
        lang = a[1] if len(a) > 1 else "ru"
        missing = check(lang)
        print("Бот готов к работе в канале." if not missing else "Не хватает прав: " + ", ".join(missing))
    elif a[:1] == ["--setup"]:
        setup(a[1], Path(a[a.index("--photo") + 1]) if "--photo" in a else None)
    elif a[:1] == ["--post"] and len(a) == 4:
        post(a[1], Path(a[2]), a[3])
    elif a[:1] == ["--file"] and len(a) == 4:
        post_file(a[1], Path(a[2]), a[3])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
