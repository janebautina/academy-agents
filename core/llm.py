"""Talk to the model through any OpenAI-compatible API (DeepSeek, OpenAI, YandexGPT, ...).

One function: chat(system, user) -> the model's answer as text. Which model and
which company serve it is decided by three lines in .env, not by the code.
"""
from __future__ import annotations

import json
import urllib.error
import urllib.request

from core import env


def chat(system: str, user: str, max_tokens: int = 1500) -> str:
    base = env.need("LLM_BASE_URL").rstrip("/")
    body = {
        "model": env.need("LLM_MODEL"),
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "max_tokens": max_tokens,
        "temperature": 0,
    }
    headers = {"Authorization": f"Bearer {env.need('LLM_API_KEY')}", "Content-Type": "application/json"}
    if env.get("LLM_FOLDER_ID"):  # YandexGPT needs the Yandex Cloud folder id
        headers["OpenAI-Project"] = env.get("LLM_FOLDER_ID")
    request = urllib.request.Request(f"{base}/chat/completions", data=json.dumps(body).encode(), headers=headers)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            answer = json.load(response)
    except urllib.error.HTTPError as e:
        hint = {401: "the key is wrong", 402: "the balance is empty, top it up", 429: "too many requests, wait a minute"}
        raise SystemExit(f"Model API error {e.code}: {hint.get(e.code, e.read().decode()[:300])}") from None
    return answer["choices"][0]["message"]["content"].strip()
