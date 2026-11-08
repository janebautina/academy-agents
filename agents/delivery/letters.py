"""Emails the delivery agent sends: access to the course, RU and EN."""
from __future__ import annotations

import html

COURSE = {"ru": "AI для бизнеса: компания на AI-агентах", "en": "AI for Your Business: the Agentic Company"}


def access(lang: str, link: str) -> tuple[str, str, str]:
    """(subject, text, html) of the access email."""
    if lang == "ru":
        subject = f"Ваш доступ к курсу «{COURSE['ru']}» · Alesha AI Academy"
        lines = [
            "Здравствуйте!",
            f"Спасибо за покупку курса «{COURSE['ru']}». Оплату получили.",
            "Ваша личная ссылка в закрытый Telegram-канал курса:",
            link,
            "Как всё устроено:",
            "• Ссылка на одного человека и действует 7 дней. Не пересылайте её: второй человек по ней не войдёт.",
            "• В канале сразу открыты все готовые уроки, видео-практика и шаблоны. Новые уроки приходят туда же, без доплаты.",
            "• Код компании из курса: https://github.com/janebautina/academy-agents",
            "• Вопрос или что-то не открывается — просто ответьте на это письмо.",
            "До встречи в канале!",
            "Евгения, Alesha AI Academy",
        ]
    else:
        subject = f"Your access to \"{COURSE['en']}\" · Alesha AI Academy"
        lines = [
            "Hi there,",
            f"Thank you for buying \"{COURSE['en']}\". Your payment came through.",
            "Your personal link to the private Telegram channel of the course:",
            link,
            "How it works:",
            "• The link works for one person and expires in 7 days. Please don't forward it: a second person can't join with it.",
            "• All finished lessons, the step-by-step practice videos and templates are in the channel. New lessons arrive there at no extra cost.",
            "• The company's code: https://github.com/janebautina/academy-agents",
            "• Questions, or something doesn't open? Just reply to this email.",
            "See you inside,",
            "Evgeniya, Alesha AI Academy",
        ]
    text = "\n\n".join(lines)
    body = "".join(
        f'<p><a href="{html.escape(link)}" style="display:inline-block;padding:12px 20px;background:#1f2a44;color:#fff;'
        f'border-radius:8px;text-decoration:none;font-weight:bold">{"Войти в канал курса" if lang == "ru" else "Join the course channel"}</a></p>'
        if line == link else f"<p>{html.escape(line)}</p>" for line in lines)
    return subject, text, f'<div style="font-family:Arial,sans-serif;font-size:16px;line-height:1.5;color:#1f2a44">{body}</div>'
