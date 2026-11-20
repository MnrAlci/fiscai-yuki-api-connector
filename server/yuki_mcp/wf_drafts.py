"""Concept-e-mails voor de workflows-module. Standaard een .eml-bestand (X-Unsent) op schijf; optioneel een concept in
Outlook (Microsoft Graph), Gmail of AgentMail. Er wordt NIETS verstuurd, behalve via de SMTP-adapter en alleen als de
verzendbeveiliging (config + opdrachtregel + bevestiging per run) volledig is doorlopen. Verzenden naar klanten is de
verantwoordelijkheid van de gebruiker. Tokens/wachtwoorden komen uit omgevingsvariabelen waarvan de NAAM in de config staat.
Outlook, Gmail en AgentMail: verify current docs.
"""
from __future__ import annotations

import base64
import json
import os
import re
from dataclasses import dataclass, field
from email.message import EmailMessage
from pathlib import Path
from typing import Callable, Optional

HttpPost = Callable[[str, dict, dict], tuple]  # (url, headers, json_body) -> (status, text)


class DraftError(Exception):
    pass


class SendRefused(DraftError):
    pass


@dataclass
class Draft:
    to: list = field(default_factory=list)
    subject: str = ""
    body: str = ""
    cc: list = field(default_factory=list)


def default_post(url: str, headers: dict, body: dict) -> tuple:
    import httpx
    r = httpx.post(url, headers=headers, json=body, timeout=30.0)
    return r.status_code, r.text


def to_message(d: Draft, sender: str = "") -> EmailMessage:
    m = EmailMessage()
    if sender:
        m["From"] = sender
    if d.to:
        m["To"] = ", ".join(d.to)
    if d.cc:
        m["Cc"] = ", ".join(d.cc)
    m["Subject"] = d.subject
    m["X-Unsent"] = "1"  # Outlook opent dit als concept
    m.set_content(d.body)
    return m


def slug(text: str) -> str:
    return re.sub(r"[^A-Za-z0-9]+", "-", text).strip("-")[:60] or "concept"


class EmlAdapter:
    name = "eml"
    can_send = False

    def __init__(self, out_dir: Path, sender: str = "") -> None:
        self.out_dir, self.sender = Path(out_dir), sender

    def draft(self, d: Draft, name: str) -> str:
        self.out_dir.mkdir(parents=True, exist_ok=True)
        p = self.out_dir / f"{slug(name)}.eml"
        p.write_bytes(bytes(to_message(d, self.sender)))
        return str(p)


class SmtpAdapter(EmlAdapter):
    """Concept = .eml; verzenden kan alleen via send() na de verzendbeveiliging. Gegevens uit omgevingsvariabelen (namen in config)."""
    name = "smtp"
    can_send = True

    def __init__(self, out_dir: Path, sender: str, host_env: str, user_env: str, password_env: str, port: int = 587, env=None, smtp_factory=None) -> None:
        super().__init__(out_dir, sender)
        self.host_env, self.user_env, self.password_env, self.port = host_env, user_env, password_env, port
        self.env = env if env is not None else os.environ
        self.smtp_factory = smtp_factory

    def send(self, d: Draft) -> None:
        host = self.env.get(self.host_env)
        if not host or not self.sender:
            raise DraftError(f"SMTP vraagt omgevingsvariabele {self.host_env} en een afzender (sender) in de config.")
        import smtplib
        factory = self.smtp_factory or smtplib.SMTP
        with factory(host, self.port, timeout=30) as s:
            s.starttls()
            user, pw = self.env.get(self.user_env), self.env.get(self.password_env)
            if user and pw:
                s.login(user, pw)
            msg = to_message(d, self.sender)
            del msg["X-Unsent"]
            s.send_message(msg)


class _HttpDraft:
    can_send = False

    def __init__(self, token_env: str, http_post: Optional[HttpPost] = None, env=None, sender: str = "") -> None:
        self.token_env, self.http_post, self.sender = token_env, http_post or default_post, sender
        self.env = env if env is not None else os.environ

    def _token(self) -> str:
        t = self.env.get(self.token_env)
        if not t:
            raise DraftError(f"Omgevingsvariabele {self.token_env} is niet ingesteld.")
        return t

    def _post(self, url: str, body: dict) -> str:
        status, text = self.http_post(url, {"Authorization": f"Bearer {self._token()}", "Content-Type": "application/json"}, body)
        if status not in (200, 201):
            raise DraftError(f"{self.name}: HTTP {status} bij het maken van het concept.")
        return text


class OutlookAdapter(_HttpDraft):
    """Microsoft Graph: POST /me/messages maakt een concept in Concepten (verstuurt niet). Scope Mail.ReadWrite. Verify current docs."""
    name = "outlook"

    def draft(self, d: Draft, name: str) -> str:
        body = {"subject": d.subject, "body": {"contentType": "Text", "content": d.body},
                "toRecipients": [{"emailAddress": {"address": a}} for a in d.to], "ccRecipients": [{"emailAddress": {"address": a}} for a in d.cc]}
        self._post("https://graph.microsoft.com/v1.0/me/messages", body)
        return "outlook:concept"


class GmailAdapter(_HttpDraft):
    """Gmail API: users.drafts.create (verstuurt niet). Scope gmail.compose. Verify current docs."""
    name = "gmail"

    def draft(self, d: Draft, name: str) -> str:
        m = to_message(d, self.sender)
        del m["X-Unsent"]
        raw = base64.urlsafe_b64encode(bytes(m)).decode("ascii")
        self._post("https://gmail.googleapis.com/gmail/v1/users/me/drafts", {"message": {"raw": raw}})
        return "gmail:concept"


class AgentMailAdapter(_HttpDraft):
    """AgentMail: concept in een eigen inbox (POST /v0/inboxes/{inbox_id}/drafts). Inbox-id uit omgevingsvariabele. Verify current docs."""
    name = "agentmail"

    def __init__(self, token_env: str, inbox_env: str, base_url: str = "https://api.agentmail.to", http_post=None, env=None, sender: str = "") -> None:
        super().__init__(token_env, http_post, env, sender)
        self.inbox_env, self.base_url = inbox_env, base_url.rstrip("/")

    def draft(self, d: Draft, name: str) -> str:
        inbox = self.env.get(self.inbox_env)
        if not inbox:
            raise DraftError(f"Omgevingsvariabele {self.inbox_env} is niet ingesteld.")
        if not self.base_url.startswith("https://"):
            raise DraftError("AgentMail base_url moet https zijn.")
        self._post(f"{self.base_url}/v0/inboxes/{inbox}/drafts", {"to": d.to, "cc": d.cc, "subject": d.subject, "text": d.body})
        return "agentmail:concept"


def make_drafter(cfg: dict, out_dir: Path, http_post: Optional[HttpPost] = None, env=None, smtp_factory=None):
    kind = (cfg.get("adapter") or "eml").lower()
    sender = cfg.get("sender", "")
    if kind == "eml":
        return EmlAdapter(out_dir, sender)
    if kind == "smtp":
        return SmtpAdapter(out_dir, sender, cfg.get("host_env", "YUKI_WF_SMTP_HOST"), cfg.get("user_env", "YUKI_WF_SMTP_USER"),
                           cfg.get("password_env", "YUKI_WF_SMTP_PASSWORD"), int(cfg.get("port", 587)), env, smtp_factory)
    if kind == "outlook":
        return OutlookAdapter(cfg.get("token_env", "YUKI_WF_GRAPH_MAIL_TOKEN"), http_post, env, sender)
    if kind == "gmail":
        return GmailAdapter(cfg.get("token_env", "YUKI_WF_GMAIL_TOKEN"), http_post, env, sender)
    if kind == "agentmail":
        return AgentMailAdapter(cfg.get("token_env", "YUKI_WF_AGENTMAIL_TOKEN"), cfg.get("inbox_env", "YUKI_WF_AGENTMAIL_INBOX"),
                                cfg.get("base_url", "https://api.agentmail.to"), http_post, env, sender)
    raise DraftError(f"Onbekende mail-adapter '{kind}'. Kies eml, smtp, outlook, gmail of agentmail.")


def send_allowed(mail_cfg: dict, want_send: bool, confirmed: bool, interactive: bool = False, ask: Optional[Callable[[str], str]] = None) -> bool:
    """Drie sloten: config allow_send = true, --send, en bevestiging per run (--confirm-send, of 'VERSTUUR' typen in een terminal)."""
    if not want_send:
        return False
    if mail_cfg.get("allow_send") is not True:
        raise SendRefused("Verzenden staat uit: zet [mail] allow_send = true in de config (bewuste keuze).")
    if confirmed:
        return True
    if interactive and ask:
        return ask("Typ VERSTUUR om de e-mails te versturen: ").strip() == "VERSTUUR"
    raise SendRefused("Verzenden vraagt een bevestiging per run: gebruik --confirm-send of voer de opdracht in een terminal uit.")
