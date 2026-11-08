"""Connect DonationAlerts once: get DA_ACCESS_TOKEN for the delivery agent.

    python3 -m agents.delivery.auth

1. Create an app at https://www.donationalerts.com/application/clients
   (name: Alesha AI Academy, Redirect URL: https://aleshaai.com/).
2. Run this command and paste the App ID and API Key when asked (the key is not shown on screen).
3. It opens the DonationAlerts permission page: press Allow. The browser lands on aleshaai.com
   with ?code=... in the address bar — copy the whole address and paste it here.
4. The token is written into .env as DA_ACCESS_TOKEN. Nothing is printed.
"""
from __future__ import annotations

import getpass
import json
import re
import urllib.parse
import urllib.request
import webbrowser

from core.env import ROOT

REDIRECT = "https://aleshaai.com/"
SCOPE = "oauth-user-show oauth-donation-index"


def save_env(name: str, value: str) -> None:
    path = ROOT / ".env"
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    line = f"{name}={value}"
    text = re.sub(rf"^{name}=.*$", line, text, flags=re.M) if re.search(rf"^{name}=", text, re.M) else text.rstrip("\n") + f"\n{line}\n"
    path.write_text(text, encoding="utf-8")
    path.chmod(0o600)


def main() -> None:
    client_id = input("App ID: ").strip()
    secret = getpass.getpass("API Key (не отображается): ").strip()
    url = "https://www.donationalerts.com/oauth/authorize?" + urllib.parse.urlencode(
        {"client_id": client_id, "redirect_uri": REDIRECT, "response_type": "code", "scope": SCOPE})
    print("\nОткрываю страницу разрешения. Нажмите Allow, потом скопируйте адрес страницы, куда вас перенесло.")
    webbrowser.open(url)
    back = input("\nАдрес страницы (с ?code=...): ").strip()
    code = urllib.parse.parse_qs(urllib.parse.urlparse(back).query).get("code", [back])[0]
    body = urllib.parse.urlencode({"grant_type": "authorization_code", "client_id": client_id, "client_secret": secret,
                                   "redirect_uri": REDIRECT, "code": code}).encode()
    with urllib.request.urlopen(urllib.request.Request("https://www.donationalerts.com/oauth/token", data=body), timeout=30) as r:
        token = json.load(r)
    save_env("DA_ACCESS_TOKEN", token["access_token"])
    save_env("DA_REFRESH_TOKEN", token.get("refresh_token", ""))
    days = int(token.get("expires_in", 0)) // 86400
    print(f"\nГотово: DonationAlerts подключён, ключ записан в .env (действует ~{days} дн.).")


if __name__ == "__main__":
    main()
