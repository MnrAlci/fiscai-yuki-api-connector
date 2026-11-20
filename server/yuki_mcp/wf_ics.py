"""Minimale iCalendar-lezer (RFC 5545) voor de workflows-module: geen netwerk, geen extra pakketten.

Ondersteund: VEVENT met SUMMARY, DTSTART/DTEND (UTC, TZID, floating, hele dag), ATTENDEE, ORGANIZER, LOCATION,
DESCRIPTION, UID en eenvoudige RRULE (DAILY, WEEKLY met BYDAY, MONTHLY, YEARLY; INTERVAL, COUNT, UNTIL) plus EXDATE.
Niet ondersteund: BYSETPOS, BYMONTHDAY-reeksen, RDATE, aangepaste wijzigingen per exemplaar (RECURRENCE-ID). Dat staat in docs/AUTOMATION.md.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from typing import Iterator, Optional

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

# Windows-tijdzonenamen (Outlook-export) naar IANA; onbekende namen vallen terug op de standaardzone.
WINDOWS_TZ = {"Romance Standard Time": "Europe/Brussels", "W. Europe Standard Time": "Europe/Brussels", "Central Europe Standard Time": "Europe/Brussels",
              "GMT Standard Time": "Europe/London", "UTC": "UTC"}
DAYS = {"MO": 0, "TU": 1, "WE": 2, "TH": 3, "FR": 4, "SA": 5, "SU": 6}


def get_tz(name: str):
    name = WINDOWS_TZ.get(name, name)
    if name.upper() == "UTC" or ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name)
    except Exception:  # noqa: BLE001 - ontbrekende tzdata of onbekende naam
        return timezone.utc


@dataclass
class Event:
    uid: str
    summary: str
    start: datetime
    end: datetime
    attendees: list = field(default_factory=list)
    organizer: str = ""
    location: str = ""
    description: str = ""
    all_day: bool = False

    @property
    def key(self) -> str:
        return f"{self.uid}@{self.start.date().isoformat()}"


def unfold(text: str) -> list[str]:
    out: list[str] = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw[:1] in (" ", "\t") and out:
            out[-1] += raw[1:]
        else:
            out.append(raw)
    return out


def _unescape(v: str) -> str:
    return v.replace("\\n", "\n").replace("\\N", "\n").replace("\\,", ",").replace("\\;", ";").replace("\\\\", "\\")


def _split(line: str) -> tuple[str, dict, str]:
    head, _, value = line.partition(":")
    parts = head.split(";")
    params = {}
    for p in parts[1:]:
        k, _, v = p.partition("=")
        params[k.upper()] = v.strip('"')
    return parts[0].upper(), params, value


def _dt(value: str, params: dict, default_tz) -> tuple[datetime, bool]:
    value = value.strip()
    if params.get("VALUE") == "DATE" or (len(value) == 8 and value.isdigit()):
        d = datetime.strptime(value[:8], "%Y%m%d")
        return d.replace(tzinfo=default_tz), True
    if value.endswith("Z"):
        return datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc).astimezone(default_tz), False
    naive = datetime.strptime(value[:15], "%Y%m%dT%H%M%S")
    tz = get_tz(params["TZID"]) if "TZID" in params else default_tz
    return naive.replace(tzinfo=tz).astimezone(default_tz), False


def _emails(vals: list[str]) -> list[str]:
    out = []
    for v in vals:
        m = re.search(r"mailto:([^\s;]+)", v, re.I)
        if m:
            out.append(m.group(1).lower())
    return out


def parse_ics(text: str, tz_name: str = "Europe/Brussels") -> list[Event]:
    tz = get_tz(tz_name)
    events: list[Event] = []
    cur: Optional[dict] = None
    for line in unfold(text):
        if not line.strip():
            continue
        if line.strip().upper() == "BEGIN:VEVENT":
            cur = {"attendees": [], "exdates": []}
            continue
        if line.strip().upper() == "END:VEVENT":
            if cur and cur.get("start"):
                start, all_day = cur["start"]
                end = cur.get("end", (start + (timedelta(days=1) if all_day else timedelta(hours=1)), all_day))[0]
                ev = Event(cur.get("uid") or f"{cur.get('summary', '')}-{start.isoformat()}", cur.get("summary", ""), start, end, cur["attendees"],
                           cur.get("organizer", ""), cur.get("location", ""), cur.get("description", ""), all_day)
                ev.rrule = cur.get("rrule")  # type: ignore[attr-defined]
                ev.exdates = cur["exdates"]  # type: ignore[attr-defined]
                events.append(ev)
            cur = None
            continue
        if cur is None:
            continue
        name, params, value = _split(line)
        if name == "SUMMARY":
            cur["summary"] = _unescape(value)
        elif name == "UID":
            cur["uid"] = value.strip()
        elif name == "LOCATION":
            cur["location"] = _unescape(value)
        elif name == "DESCRIPTION":
            cur["description"] = _unescape(value)
        elif name == "DTSTART":
            cur["start"] = _dt(value, params, tz)
        elif name == "DTEND":
            cur["end"] = _dt(value, params, tz)
        elif name == "ATTENDEE":
            cur["attendees"] += _emails([value])
        elif name == "ORGANIZER":
            cur["organizer"] = (_emails([value]) or [""])[0]
        elif name == "RRULE":
            cur["rrule"] = dict(p.split("=", 1) for p in value.split(";") if "=" in p)
        elif name == "EXDATE":
            for v in value.split(","):
                try:
                    cur["exdates"].append(_dt(v, params, tz)[0].date())
                except ValueError:
                    pass
    return events


def _occurrences(ev: Event, window_start: datetime, window_end: datetime) -> Iterator[Event]:
    rule = getattr(ev, "rrule", None)
    ex = set(getattr(ev, "exdates", []))
    dur = ev.end - ev.start
    if not rule:
        if ev.start < window_end and ev.end >= window_start and ev.start.date() not in ex:
            yield ev
        return
    freq = rule.get("FREQ", "")
    interval = max(1, int(rule.get("INTERVAL", "1")))
    count = int(rule["COUNT"]) if "COUNT" in rule else None
    until = None
    if "UNTIL" in rule:
        until = _dt(rule["UNTIL"], {}, ev.start.tzinfo)[0]
    byday = [DAYS[d[-2:]] for d in rule.get("BYDAY", "").split(",") if d[-2:] in DAYS]
    n = 0
    base = ev.start
    cur = base
    for _ in range(5000):  # harde bovengrens: nooit eindeloos lussen
        cands = [cur]
        if freq == "WEEKLY" and byday:
            monday = cur - timedelta(days=cur.weekday())
            cands = [monday + timedelta(days=d) for d in sorted(byday)]
        for c in cands:
            if c < base:
                continue
            if until and c > until:
                return
            n += 1
            if count and n > count:
                return
            if c >= window_end:
                return
            if c + dur >= window_start and c.date() not in ex:
                o = Event(ev.uid, ev.summary, c, c + dur, ev.attendees, ev.organizer, ev.location, ev.description, ev.all_day)
                yield o
        if freq == "DAILY":
            cur = cur + timedelta(days=interval)
        elif freq == "WEEKLY":
            cur = cur + timedelta(weeks=interval)
        elif freq == "MONTHLY":
            m = cur.month - 1 + interval
            y, mo = cur.year + m // 12, m % 12 + 1
            try:
                cur = cur.replace(year=y, month=mo)
            except ValueError:  # 31e in een korte maand: sla over
                cur = cur.replace(year=y, month=mo, day=28)
        elif freq == "YEARLY":
            try:
                cur = cur.replace(year=cur.year + interval)
            except ValueError:
                cur = cur.replace(year=cur.year + interval, day=28)
        else:
            return


def in_window(events: list[Event], window_start: datetime, window_end: datetime) -> list[Event]:
    out: list[Event] = []
    for ev in events:
        out.extend(_occurrences(ev, window_start, window_end))
    return sorted(out, key=lambda e: e.start)
