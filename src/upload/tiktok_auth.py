"""TikTok OAuth-Helfer: erzeugt pro Konto Access- & Refresh-Token zum Einfügen in .env.

Hintergrund: Client Key/Secret identifizieren deine APP. Zum Posten auf ein bestimmtes
Konto (Trymacs, Eligella, Sidney) braucht es zusätzlich ein Access-Token, das nur durch
den Login (OAuth-Einwilligung) des jeweiligen Kontos entsteht.

Ablauf (lokal auf deinem Rechner):
  python3 -m src.cli auth --creator trymacs
-> öffnet die TikTok-Login-Seite, das Konto bestätigt, Tokens werden ausgegeben.
"""
from __future__ import annotations

import urllib.parse
from typing import Optional

AUTHORIZE = "https://www.tiktok.com/v2/auth/authorize/"
TOKEN = "https://open.tiktokapis.com/v2/oauth/token/"
DEFAULT_SCOPES = ["user.info.basic", "video.publish", "video.list"]


def build_auth_url(client_key: str, redirect_uri: str, scopes, state: str) -> str:
    params = {
        "client_key": client_key,
        "scope": ",".join(scopes),
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "state": state,
    }
    return f"{AUTHORIZE}?{urllib.parse.urlencode(params)}"


def exchange_code(client_key: str, client_secret: str, code: str, redirect_uri: str) -> dict:
    import requests  # lazy

    r = requests.post(
        TOKEN,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": redirect_uri,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def refresh_access_token(client_key: str, client_secret: str, refresh_token: str) -> dict:
    import requests  # lazy

    r = requests.post(
        TOKEN,
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data={
            "client_key": client_key,
            "client_secret": client_secret,
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        timeout=30,
    )
    r.raise_for_status()
    return r.json()


def _wait_for_code(redirect_uri: str, timeout_sec: int = 300) -> Optional[str]:
    """Startet einen lokalen Server auf der Redirect-URI und fängt ?code=... ab."""
    import http.server
    import socketserver
    from urllib.parse import urlparse, parse_qs

    parsed = urlparse(redirect_uri)
    host = parsed.hostname or "localhost"
    port = parsed.port or 8080
    path = parsed.path or "/callback"
    holder: dict[str, Optional[str]] = {"code": None, "error": None}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            if urlparse(self.path).path == path:
                holder["code"] = (q.get("code") or [None])[0]
                holder["error"] = (q.get("error") or [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                msg = "✅ Geschafft – du kannst dieses Fenster schließen." if holder["code"] \
                    else f"❌ Fehler: {holder['error']}"
                self.wfile.write(f"<html><body><h2>{msg}</h2></body></html>".encode("utf-8"))
            else:
                self.send_response(404)
                self.end_headers()

        def log_message(self, *args):  # Server still halten
            pass

    with socketserver.TCPServer((host, port), Handler) as httpd:
        httpd.timeout = timeout_sec
        print(f"[auth] Warte auf TikTok-Rückruf an {redirect_uri} ...")
        httpd.handle_request()  # blockiert bis zum ersten Callback
    return holder["code"]


def run_oauth(
    creator_id: str,
    client_key: str,
    client_secret: str,
    redirect_uri: str,
    scopes=None,
    manual: bool = False,
) -> dict:
    """Führt den OAuth-Flow durch und gibt die fertigen .env-Zeilen aus."""
    scopes = scopes or DEFAULT_SCOPES
    state = f"st_{creator_id}"
    url = build_auth_url(client_key, redirect_uri, scopes, state)

    print("\n1) Öffne diese URL im Browser und logge dich mit dem Ziel-Konto ein:\n")
    print(url, "\n")
    try:
        import webbrowser

        webbrowser.open(url)
    except Exception:
        pass

    if manual:
        pasted = input("2) Füge hier die komplette Redirect-URL (oder den ?code=...) ein:\n> ").strip()
        from urllib.parse import urlparse, parse_qs

        code = (parse_qs(urlparse(pasted).query).get("code") or [pasted])[0]
    else:
        code = _wait_for_code(redirect_uri)

    if not code:
        raise RuntimeError("Kein Autorisierungs-Code erhalten.")

    tok = exchange_code(client_key, client_secret, code, redirect_uri)
    access = tok.get("access_token")
    refresh = tok.get("refresh_token")
    if not access:
        raise RuntimeError(f"Token-Tausch fehlgeschlagen: {tok}")

    cid = creator_id.upper()
    print("\n✅ Erfolgreich! Füge diese Zeilen in deine .env ein:\n")
    print(f"TIKTOK_ACCESS_TOKEN_{cid}={access}")
    print(f"TIKTOK_REFRESH_TOKEN_{cid}={refresh}")
    print(f"\n(open_id={tok.get('open_id')}, scope={tok.get('scope')}, "
          f"gültig {tok.get('expires_in')}s)")
    return tok
