"""Gedeelde antwoordcache voor Yuki-leesresultaten.

- Sleutel: SHA-256 van (domein, administratie, service, methode, parameters).
  ``sessionID``/``accessKey`` gaan nooit mee in de sleutel of in het bestand.
- Standaardmap ``~/.fiscai-yuki-api-connector/cache/`` (0700; bestanden 0600): geen
  geheimen, wel vertrouwelijke dossierdata.
- TTL: 24 uur voor afgesloten periodes (alle datums vóór de eerste dag van de
  lopende maand, Europe/Brussels) en voor stamgegevens; 1 uur voor lopende
  periodes, openstaande posten en wijzigingsdatums.
- Een cache-hit verstuurt niets en telt dus niet mee in de dagteller.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import logging
import os
import tempfile
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable, Optional, Sequence
from xml.etree import ElementTree as ET

from .paths import secure_dir
from .soap import Param, format_value

log = logging.getLogger("yuki_core.response_cache")

TZ_NAME = "Europe/Brussels"
TTL_CLOSED = timedelta(hours=24)
TTL_OPEN = timedelta(hours=1)
_SECRET_PARAMS = {"sessionid", "accesskey", "clientsecret"}
# Altijd 'lopend' (inhoud verandert dagelijks), ongeacht datums.
ALWAYS_OPEN = {"GetFinancialYearModifiedDate", "OutstandingDebtorItems", "OutstandingCreditorItems"}
# Nooit cachen.
NEVER_CACHE = {"Authenticate"}

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _tz():
    from zoneinfo import ZoneInfo
    return ZoneInfo(TZ_NAME)


def clean_params(params: Sequence[Param]) -> list[tuple[str, str]]:
    return [(n, format_value(v)) for n, v in params
            if v is not None and n.lower() not in _SECRET_PARAMS]


def cache_key(domain: str, administration_id: Optional[str], service: str, method: str,
              params: Sequence[Param]) -> str:
    payload = json.dumps([domain, administration_id or "", service, method,
                          clean_params(params)], separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def default_ttl(method: str, params: Sequence[Param], now: datetime) -> timedelta:
    if method in ALWAYS_OPEN:
        return TTL_OPEN
    dates = [v.date() if isinstance(v, datetime) else v
             for _, v in params if isinstance(v, (date, datetime))]
    if not dates:
        return TTL_CLOSED          # stamgegevens (administraties, rekeningschema, ...)
    local_today = now.astimezone(_tz()).date()
    month_start = local_today.replace(day=1)
    return TTL_CLOSED if max(dates) < month_start else TTL_OPEN


@dataclass
class CacheHit:
    result: Optional[ET.Element]
    stored_at: datetime
    expires_at: datetime


class ResponseCache:
    def __init__(self, cache_dir: Optional[Path | str] = None, clock: Clock = _utcnow) -> None:
        if cache_dir is None:
            from .paths import default_response_cache_dir
            cache_dir = default_response_cache_dir()
        self.dir = secure_dir(cache_dir)
        self._clock = clock

    def _path(self, key: str) -> Path:
        return self.dir / key[:2] / f"{key}.json"

    def get(self, key: str) -> Optional[CacheHit]:
        p = self._path(key)
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except FileNotFoundError:
            return None
        except (OSError, ValueError):
            with contextlib.suppress(OSError):
                p.unlink()
            return None
        expires = datetime.fromisoformat(data["expires_at"])
        if self._clock() >= expires:
            return None
        xml = data.get("result_xml")
        return CacheHit(ET.fromstring(xml) if xml else None,
                        datetime.fromisoformat(data["stored_at"]), expires)

    def put(self, key: str, *, domain: str, administration_id: Optional[str], service: str,
            method: str, result: Optional[ET.Element], ttl: timedelta) -> None:
        now = self._clock()
        p = self._path(key)
        secure_dir(p.parent)
        data = {"domain": domain, "administration_id": administration_id, "service": service,
                "method": method, "stored_at": now.isoformat(),
                "expires_at": (now + ttl).isoformat(),
                "result_xml": ET.tostring(result, encoding="unicode") if result is not None else None}
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=".json")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.chmod(tmp, 0o600)
            os.replace(tmp, p)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def stats(self) -> dict[str, dict[str, int]]:
        """Per domein: aantal entries, geldig, bytes. Geen inhoud of cijfers."""
        out: dict[str, dict[str, int]] = {}
        now = self._clock()
        for p in self.dir.glob("*/*.json"):
            try:
                data = json.loads(p.read_text(encoding="utf-8"))
                dom = data.get("domain") or "?"
                valid = now < datetime.fromisoformat(data["expires_at"])
            except (OSError, ValueError, KeyError):
                dom, valid = "?", False
            s = out.setdefault(dom, {"entries": 0, "valid": 0, "bytes": 0})
            s["entries"] += 1
            s["valid"] += int(valid)
            with contextlib.suppress(OSError):
                s["bytes"] += p.stat().st_size
        return out

    def purge_expired(self) -> int:
        n, now = 0, self._clock()
        for p in self.dir.glob("*/*.json"):
            try:
                if now >= datetime.fromisoformat(json.loads(p.read_text())["expires_at"]):
                    p.unlink(); n += 1
            except (OSError, ValueError, KeyError):
                with contextlib.suppress(OSError):
                    p.unlink(); n += 1
        return n
