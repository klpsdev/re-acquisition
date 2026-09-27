#!/usr/bin/env python3
"""One-time Gmail authorization for the SPREV Acquisition Engine.

Run this on your own computer (it opens a browser), not on Render:

    python backend/scripts/gmail_auth.py --client-id XXX.apps.googleusercontent.com --client-secret YYY

It asks Google for permission to *send* email as you (scope gmail.send: it can't
read your inbox), prints a refresh token, and sends you a test email to prove
the token works. Paste the printed values into Render → sprev-api → Environment.

Needs only the Python standard library.
"""
from __future__ import annotations

import argparse
import base64
import hashlib
import http.server
import json
import secrets
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from email.message import EmailMessage

AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
SCOPE = "https://www.googleapis.com/auth/gmail.send"


def post(url: str, data: dict | None = None, token: str | None = None, body: dict | None = None) -> dict:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    if body is not None:
        payload, headers["Content-Type"] = json.dumps(body).encode(), "application/json"
    else:
        payload = urllib.parse.urlencode(data or {}).encode()
    req = urllib.request.Request(url, data=payload, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        sys.exit(f"\nGoogle returned {e.code}: {e.read().decode()[:400]}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--client-id", required=True, help="OAuth client ID (Desktop app type)")
    ap.add_argument("--client-secret", required=True)
    ap.add_argument("--port", type=int, default=8765)
    ap.add_argument("--no-test", action="store_true", help="skip sending the test email to yourself")
    args = ap.parse_args()

    redirect = f"http://127.0.0.1:{args.port}/"
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    result: dict = {}

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):  # noqa: N802
            q = urllib.parse.parse_qs(urllib.parse.urlparse(self.path).query)
            result.update({k: v[0] for k, v in q.items()})
            ok = "code" in q and q.get("state", [""])[0] == state
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            msg = "Authorized. You can close this tab and return to the terminal." if ok else \
                f"Authorization failed: {result.get('error', 'state mismatch')}. Return to the terminal."
            self.wfile.write(f"<p style='font:16px system-ui;margin:40px'>{msg}</p>".encode())
            threading.Thread(target=self.server.shutdown, daemon=True).start()

        def log_message(self, *a):
            pass

    server = http.server.HTTPServer(("127.0.0.1", args.port), Handler)
    url = AUTH_URL + "?" + urllib.parse.urlencode({
        "client_id": args.client_id, "redirect_uri": redirect, "response_type": "code", "scope": SCOPE,
        "access_type": "offline", "prompt": "consent", "state": state,
        "code_challenge": challenge, "code_challenge_method": "S256",
    })
    print("\nOpening Google sign-in. If the browser doesn't open, paste this URL into it:\n\n" + url + "\n")
    print('If Google says "Google hasn\'t verified this app": click Advanced → Go to (your app). It\'s your own app.\n')
    webbrowser.open(url)
    server.serve_forever()

    if result.get("state") != state or "code" not in result:
        sys.exit(f"Authorization didn't complete: {result.get('error', 'no code returned')}")

    tokens = post(TOKEN_URL, {
        "code": result["code"], "client_id": args.client_id, "client_secret": args.client_secret,
        "redirect_uri": redirect, "grant_type": "authorization_code", "code_verifier": verifier,
    })
    refresh = tokens.get("refresh_token")
    if not refresh:
        sys.exit("Google didn't return a refresh token. Remove the app's access at "
                 "https://myaccount.google.com/permissions and run this again.")

    if not args.no_test:
        sender = input("Your Gmail address (the test email goes to yourself): ").strip()
        msg = EmailMessage()
        msg["To"] = msg["From"] = sender
        msg["Subject"] = "SPREV Acquisition Engine: Gmail sending works"
        msg.set_content("This test confirms the app can send offer letters from your Gmail account.")
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        post(SEND_URL, token=tokens["access_token"], body={"raw": raw})
        print(f"\nTest email sent to {sender}. Check your inbox.")
    else:
        sender = "<your Gmail address>"

    print("\nAdd these to Render → sprev-api → Environment, then Save, rebuild, and deploy:\n")
    print(f"  GMAIL_CLIENT_ID={args.client_id}")
    print(f"  GMAIL_CLIENT_SECRET={args.client_secret}")
    print(f"  GMAIL_REFRESH_TOKEN={refresh}")
    print(f"  GMAIL_SENDER={sender}")
    print("\nKeep the refresh token private: it lets anyone holding it send email as you.")


if __name__ == "__main__":
    main()
