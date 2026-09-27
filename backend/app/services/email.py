"""Outbound email for offer letters.

Two providers, picked automatically from the environment:

  gmail_api  Sends as you through the Gmail API over HTTPS. Works on Render's free
             plan (which blocks SMTP ports). Messages land in your Gmail Sent folder
             and replies come back to your inbox.
             Needs GMAIL_CLIENT_ID, GMAIL_CLIENT_SECRET, GMAIL_REFRESH_TOKEN, GMAIL_SENDER.
             Get the refresh token once with:  python backend/scripts/gmail_auth.py

  smtp       Any SMTP server (Gmail with an app password, SendGrid, ...). Only on hosts
             that allow outbound SMTP (Render paid plans, your own machine).
             Needs SMTP_HOST, SMTP_PORT, SMTP_USERNAME, SMTP_PASSWORD, and GMAIL_SENDER or SMTP_FROM.
"""
from __future__ import annotations

import base64
import logging
import re
import smtplib
import ssl
import threading
import time
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

import httpx

from ..config import Settings

log = logging.getLogger(__name__)

TOKEN_URL = "https://oauth2.googleapis.com/token"
SEND_URL = "https://gmail.googleapis.com/gmail/v1/users/me/messages/send"
EMAIL_RE = re.compile(r"^[^@\s,;<>]+@[^@\s,;<>]+\.[A-Za-z]{2,}$")


class EmailError(RuntimeError):
    """A send failed. The message explains why in plain words."""


@dataclass
class SentMessage:
    provider: str
    message_id: str
    thread_id: str | None = None


PLACEHOLDER_RE = re.compile(r"\[[A-Z][^\]\n]{1,40}\]")


def placeholders(text: str) -> list[str]:
    """Unfilled template fields like [Your name] that must not reach an agent."""
    return sorted(set(PLACEHOLDER_RE.findall(text)))


def valid_email(addr: str | None) -> bool:
    return bool(addr and EMAIL_RE.match(addr.strip()))


def build_message(sender: str, sender_name: str | None, to: str, subject: str, body: str,
                  cc: list[str] | None = None) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = formataddr((sender_name, sender)) if sender_name else sender
    msg["To"] = to
    if cc:
        msg["Cc"] = ", ".join(cc)
    msg["Reply-To"] = sender
    msg["Subject"] = subject
    msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1])
    msg.set_content(body)
    return msg


class GmailApiMailer:
    provider = "gmail_api"

    def __init__(self, s: Settings, client: httpx.Client | None = None) -> None:
        self.s = s
        self.http = client or httpx.Client(timeout=30)
        self._token: str | None = None
        self._expires = 0.0
        self._lock = threading.Lock()

    @property
    def sender(self) -> str:
        return self.s.gmail_sender or ""

    def _access_token(self) -> str:
        with self._lock:
            if self._token and time.time() < self._expires:
                return self._token
            r = self.http.post(TOKEN_URL, data={
                "client_id": self.s.gmail_client_id, "client_secret": self.s.gmail_client_secret,
                "refresh_token": self.s.gmail_refresh_token, "grant_type": "refresh_token",
            })
            if r.status_code >= 400:
                err = r.json().get("error", "") if r.headers.get("content-type", "").startswith("application/json") else ""
                if err == "invalid_grant":
                    raise EmailError("Google rejected the saved Gmail authorization (invalid_grant). It was revoked or "
                                     "expired; if the Google Cloud app is still in Testing mode, tokens expire after "
                                     "7 days. Publish the app, then run scripts/gmail_auth.py again and update "
                                     "GMAIL_REFRESH_TOKEN.")
                raise EmailError(f"Couldn't refresh Gmail access ({r.status_code}): {r.text[:200]}")
            body = r.json()
            self._token = body["access_token"]
            self._expires = time.time() + max(60, int(body.get("expires_in", 3600)) - 60)
            return self._token

    def send(self, msg: EmailMessage) -> SentMessage:
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode()
        r = self.http.post(SEND_URL, json={"raw": raw},
                           headers={"Authorization": f"Bearer {self._access_token()}"})
        if r.status_code == 401:  # token revoked between refreshes: try once more
            self._token = None
            r = self.http.post(SEND_URL, json={"raw": raw},
                               headers={"Authorization": f"Bearer {self._access_token()}"})
        if r.status_code == 403:
            raise EmailError("Gmail refused to send (403). Check that the Gmail API is enabled in your Google Cloud "
                             "project and that the authorization included the gmail.send permission. "
                             f"Details: {r.text[:200]}")
        if r.status_code >= 400:
            raise EmailError(f"Gmail send failed ({r.status_code}): {r.text[:200]}")
        d = r.json()
        return SentMessage(provider=self.provider, message_id=d.get("id", ""), thread_id=d.get("threadId"))


class SmtpMailer:
    provider = "smtp"

    def __init__(self, s: Settings) -> None:
        self.s = s

    @property
    def sender(self) -> str:
        return self.s.smtp_from or self.s.gmail_sender or self.s.smtp_username or ""

    def send(self, msg: EmailMessage) -> SentMessage:
        ctx = ssl.create_default_context()
        try:
            if self.s.smtp_port == 465:
                with smtplib.SMTP_SSL(self.s.smtp_host, 465, context=ctx, timeout=20) as srv:
                    srv.login(self.s.smtp_username, self.s.smtp_password)
                    srv.send_message(msg)
            else:
                with smtplib.SMTP(self.s.smtp_host, self.s.smtp_port, timeout=20) as srv:
                    srv.starttls(context=ctx)
                    srv.login(self.s.smtp_username, self.s.smtp_password)
                    srv.send_message(msg)
        except (OSError, smtplib.SMTPException) as e:
            hint = " Render's free plan blocks SMTP; use the Gmail API setup instead." if isinstance(e, (TimeoutError, ConnectionError)) else ""
            raise EmailError(f"SMTP send failed: {e}.{hint}") from e
        return SentMessage(provider=self.provider, message_id=msg["Message-ID"])


Mailer = GmailApiMailer | SmtpMailer
_mailer: Mailer | None = None


def get_mailer(s: Settings) -> Mailer | None:
    """The configured mailer, or None when email isn't set up."""
    global _mailer
    if _mailer is not None:
        return _mailer
    if s.gmail_client_id and s.gmail_client_secret and s.gmail_refresh_token and s.gmail_sender:
        _mailer = GmailApiMailer(s)
    elif s.smtp_host and s.smtp_username and s.smtp_password:
        _mailer = SmtpMailer(s)
    return _mailer


def status(s: Settings) -> dict:
    m = get_mailer(s)
    return {"configured": m is not None, "provider": m.provider if m else None, "sender": m.sender if m else None}
