"""Agenda-adapters voor de workflows-module: ICS (bestand of URL), Microsoft Graph (Outlook) en Google Calendar.

Alleen lezen. Tokens komen uit omgevingsvariabelen waarvan de NAAM in de configuratie staat; nooit uit het configbestand.
Graph en Google zijn optioneel en in docs/AUTOMATION.md gemarkeerd als 'verify current docs'.
"""
from __future__ import annotations

import os
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from .wf_ics import Event, get_tz, in_window, parse_ics

HttpGet = Callable[[str, dict], tuple]  # (url, headers) -> (status, text)


class CalendarError(Exception):
    pass


def default_get(url: str, headers: dict) -> tuple:
    import httpx
    r = httpx.get(url, headers=headers, timeout=30.0, follow_redirects=False)
    return r.status_code, r.text


def _need_https(url: str) -> str:
    if url.lower().startswith("webcal://"):
        url = "https://" + url[9:]
    if not url.lower().startswith("https://"):
        raise CalendarError("Alleen https-adressen zijn toegestaan voor de agenda.")
    return url


class ICSAdapter:
    def __init__(self, path: Optional[str] = None, url_env: Optional[str] = None, tz: str = "Europe/Brussels", http_get: Optional[HttpGet] = None, env=None) -> None:
        self.path, self.url_env, self.tz, self.http_get, self.env = path, url_env, tz, http_get or default_get, env if env is not None else os.environ

    def _text(self) -> str:
        if self.path:
            return Path(self.path).expanduser().read_text(encoding="utf-8-sig")
        url = self.env.get(self.url_env or "")
        if not url:
            raise CalendarError(f"Omgevingsvariabele {self.url_env or '(url_env ontbreekt)'} is niet ingesteld.")
        status, text = self.http_get(_need_https(url), {})
        if status != 200:
            raise CalendarError(f"ICS-adres gaf HTTP {status}.")
        return text

    def events(self, start: datetime, end: datetime) -> list[Event]:
        return in_window(parse_ics(self._text(), self.tz), start, end)


def _json_get(http_get: HttpGet, url: str, headers: dict) -> dict:
    import json
    status, text = http_get(url, headers)
    if status != 200:
        raise CalendarError(f"Agenda-API gaf HTTP {status}.")
    return json.loads(text)


def _iso(value: str, tz) -> datetime:
    value = value.strip()
    if "." in value and "T" in value:  # Graph: 7 cijfers fractie
        head, _, frac = value.partition(".")
        tail = ""
        for sym in ("+", "-", "Z"):
            if sym in frac:
                i = frac.index(sym)
                frac, tail = frac[:i], frac[i:]
                break
        value = head + tail
    d = datetime.fromisoformat(value.replace("Z", "+00:00"))
    return (d if d.tzinfo else d.replace(tzinfo=timezone.utc)).astimezone(tz)


class GraphAdapter:
    """Microsoft Graph calendarView (alleen lezen). Token: omgevingsvariabele (Calendars.Read). Verify current docs."""
    BASE = "https://graph.microsoft.com/v1.0"

    def __init__(self, token_env: str = "YUKI_WF_GRAPH_TOKEN", tz: str = "Europe/Brussels", http_get: Optional[HttpGet] = None, env=None, user: str = "me") -> None:
        self.token_env, self.tz, self.http_get, self.env, self.user = token_env, tz, http_get or default_get, env if env is not None else os.environ, user

    def events(self, start: datetime, end: datetime) -> list[Event]:
        tok = self.env.get(self.token_env)
        if not tok:
            raise CalendarError(f"Omgevingsvariabele {self.token_env} is niet ingesteld.")
        tz = get_tz(self.tz)
        u = start.astimezone(timezone.utc), end.astimezone(timezone.utc)
        url = (f"{self.BASE}/{self.user}/calendarView?startDateTime={u[0].strftime('%Y-%m-%dT%H:%M:%SZ')}&endDateTime={u[1].strftime('%Y-%m-%dT%H:%M:%SZ')}"
               "&$top=100&$select=id,subject,start,end,isAllDay,attendees,organizer,location,bodyPreview")
        headers = {"Authorization": f"Bearer {tok}", "Prefer": 'outlook.timezone="UTC"'}
        out: list[Event] = []
        for _ in range(10):
            data = _json_get(self.http_get, url, headers)
            for v in data.get("value", []):
                s, e = v.get("start", {}), v.get("end", {})
                if not s.get("dateTime"):
                    continue
                emails = [a.get("emailAddress", {}).get("address", "").lower() for a in v.get("attendees", [])]
                org = v.get("organizer", {}).get("emailAddress", {}).get("address", "").lower()
                out.append(Event(v.get("id", ""), v.get("subject") or "", _iso(s["dateTime"], tz), _iso(e["dateTime"], tz) if e.get("dateTime") else _iso(s["dateTime"], tz),
                                 [x for x in emails if x], org, (v.get("location") or {}).get("displayName", ""), v.get("bodyPreview", ""), bool(v.get("isAllDay"))))
            url = data.get("@odata.nextLink") or ""
            if not url:
                break
        return sorted(out, key=lambda x: x.start)


class GoogleAdapter:
    """Google Calendar events.list (alleen lezen). Token: omgevingsvariabele (scope calendar.readonly). Verify current docs."""
    BASE = "https://www.googleapis.com/calendar/v3/calendars"

    def __init__(self, token_env: str = "YUKI_WF_GOOGLE_TOKEN", calendar_id: str = "primary", tz: str = "Europe/Brussels", http_get: Optional[HttpGet] = None, env=None) -> None:
        self.token_env, self.calendar_id, self.tz, self.http_get, self.env = token_env, calendar_id, tz, http_get or default_get, env if env is not None else os.environ

    def events(self, start: datetime, end: datetime) -> list[Event]:
        from urllib.parse import quote
        tok = self.env.get(self.token_env)
        if not tok:
            raise CalendarError(f"Omgevingsvariabele {self.token_env} is niet ingesteld.")
        tz = get_tz(self.tz)
        f = lambda d: quote(d.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))  # noqa: E731
        url = f"{self.BASE}/{quote(self.calendar_id, safe='')}/events?singleEvents=true&orderBy=startTime&maxResults=250&timeMin={f(start)}&timeMax={f(end)}"
        data = _json_get(self.http_get, url, {"Authorization": f"Bearer {tok}"})
        out: list[Event] = []
        for v in data.get("items", []):
            s, e = v.get("start", {}), v.get("end", {})
            all_day = "date" in s
            sv = s.get("dateTime") or (s.get("date") + "T00:00:00" if s.get("date") else None)
            if not sv:
                continue
            ev_ = e.get("dateTime") or (e.get("date") + "T00:00:00" if e.get("date") else sv)
            st = _iso(sv, tz) if not all_day else datetime.fromisoformat(sv).replace(tzinfo=tz)
            en = _iso(ev_, tz) if not all_day else datetime.fromisoformat(ev_).replace(tzinfo=tz)
            out.append(Event(v.get("id", ""), v.get("summary", ""), st, en, [a.get("email", "").lower() for a in v.get("attendees", []) if a.get("email")],
                             (v.get("organizer") or {}).get("email", "").lower(), v.get("location", ""), v.get("description", ""), all_day))
        return out


def make_adapter(cfg: dict, tz: str, http_get: Optional[HttpGet] = None, env=None):
    kind = (cfg.get("adapter") or "ics").lower()
    if kind == "ics":
        return ICSAdapter(cfg.get("path"), cfg.get("url_env"), tz, http_get, env)
    if kind == "graph":
        return GraphAdapter(cfg.get("token_env", "YUKI_WF_GRAPH_TOKEN"), tz, http_get, env)
    if kind == "google":
        return GoogleAdapter(cfg.get("token_env", "YUKI_WF_GOOGLE_TOKEN"), cfg.get("calendar_id", "primary"), tz, http_get, env)
    raise CalendarError(f"Onbekende agenda-adapter '{kind}'. Kies ics, graph of google.")
