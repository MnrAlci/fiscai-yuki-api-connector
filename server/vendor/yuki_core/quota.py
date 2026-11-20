"""Dagteller per Yuki-domein (harde limiet, gedeeld over processen).

- Elke echte SOAP-call (ook ``Authenticate`` en een herhaalde call na een
  sessiefout) wordt **vóór** verzending gereserveerd. Een cache-hit telt niet.
- Teller per kalenderdag in **Europe/Brussels** en per domein, in één JSON-
  bestand (standaard ``~/.fiscai-yuki-api-connector/call_counter.json``, 0600, map
  0700) met een exclusieve ``fcntl``-lock: meerdere bots/processen tellen veilig.
- Standaard limiet **900**, waarschuwing bij **720** (80 %). De 901e poging
  verstuurt niets en geeft ``YukiDailyLimitReached`` met de status.
- Geen stille omzeiling: een limiet boven 900 wordt alleen aanvaard als
  ``YUKI_DAILY_LIMIT_APPROVAL`` een akkoordreferentie bevat, en nooit boven
  1000 (gratis staffel van Yuki). Een onleesbaar tellerbestand → fail closed
  (geen call), nooit stil terug naar 0.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterator, Optional
from zoneinfo import ZoneInfo

from .errors import YukiConfigError, YukiDailyLimitReached, YukiError
from .paths import secure_dir

try:
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore

log = logging.getLogger("yuki_core.quota")

TZ = ZoneInfo("Europe/Brussels")
DEFAULT_LIMIT = 900
DEFAULT_WARN = 720
APPROVED_MAX = 1000          # gratis staffel van Yuki; nooit hoger
KEEP_DAYS = 14
MAX_BLOCKED_LOGGED = 200
COUNTER_FILE = "call_counter.json"

Clock = Callable[[], datetime]


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def limits_from_env() -> tuple[int, int]:
    """(limiet, waarschuwing) uit ``YUKI_DAILY_LIMIT`` / ``YUKI_DAILY_WARN``."""
    def _int(name: str, default: int) -> int:
        raw = os.environ.get(name, "").strip()
        if not raw:
            return default
        try:
            return int(raw)
        except ValueError as exc:
            raise YukiConfigError(f"{name} moet een geheel getal zijn") from exc

    limit = _int("YUKI_DAILY_LIMIT", DEFAULT_LIMIT)
    warn = _int("YUKI_DAILY_WARN", min(DEFAULT_WARN, int(limit * 0.8)))
    return limit, warn


def validate_limits(limit: int, warn: int, approval: Optional[str] = None) -> tuple[int, int]:
    if limit < 1:
        raise YukiConfigError("De daglimiet moet minstens 1 zijn")
    if limit > APPROVED_MAX:
        raise YukiConfigError(f"Daglimiet {limit} > {APPROVED_MAX}: buiten de gratis staffel, niet toegelaten")
    if limit > DEFAULT_LIMIT:
        approval = approval if approval is not None else os.environ.get("YUKI_DAILY_LIMIT_APPROVAL", "")
        if not (approval or "").strip():
            raise YukiConfigError(
                f"Daglimiet {limit} > {DEFAULT_LIMIT} vereist uitdrukkelijk akkoord van de gebruiker "
                "(zet YUKI_DAILY_LIMIT_APPROVAL met de akkoordreferentie)")
        log.warning("Yuki-daglimiet verhoogd naar %s (akkoord: %s)", limit, approval.strip()[:80])
    if not 0 < warn <= limit:
        raise YukiConfigError("De waarschuwingsdrempel moet tussen 1 en de limiet liggen")
    return limit, warn


@dataclass
class QuotaStatus:
    domain: str
    day: str                       # YYYY-MM-DD, Europe/Brussels
    calls: int
    authenticates: int
    limit: int
    warn_at: int
    blocked: int = 0
    open_requests: list[dict] = field(default_factory=list)

    @property
    def remaining(self) -> int:
        return max(0, self.limit - self.calls)

    @property
    def warning(self) -> bool:
        return self.calls >= self.warn_at

    @property
    def limit_reached(self) -> bool:
        return self.calls >= self.limit

    @property
    def resets_at(self) -> str:
        d = datetime.fromisoformat(self.day).replace(tzinfo=TZ) + timedelta(days=1)
        return d.isoformat()

    def to_dict(self) -> dict:
        out = asdict(self)
        out.update(remaining=self.remaining, warning=self.warning,
                   limit_reached=self.limit_reached, resets_at=self.resets_at,
                   status="daglimiet bereikt" if self.limit_reached
                   else "waarschuwing" if self.warning else "ok")
        return out


class DailyQuota:
    """Persistente, procesveilige dagteller per domein."""

    def __init__(self, data_dir: Optional[Path | str] = None, *, limit: Optional[int] = None,
                 warn_at: Optional[int] = None, approval: Optional[str] = None,
                 clock: Clock = _utcnow, persistent: bool = True) -> None:
        env_limit, env_warn = limits_from_env()
        lim = env_limit if limit is None else limit
        warn = (warn_at if warn_at is not None
                else env_warn if limit is None else min(DEFAULT_WARN, int(lim * 0.8)) or 1)
        self.limit, self.warn_at = validate_limits(lim, warn, approval)
        self._clock = clock
        self.path: Optional[Path] = None
        self._mem: dict = {"version": 1, "days": {}}
        if persistent:
            if data_dir is None:
                from .paths import default_data_dir
                data_dir = default_data_dir()
            self.path = secure_dir(data_dir) / COUNTER_FILE

    # -------------------------------------------------------------- helpers
    def today(self) -> str:
        return self._clock().astimezone(TZ).date().isoformat()

    @contextlib.contextmanager
    def _locked(self) -> Iterator[dict]:
        """Exclusieve lock → data lezen → aanpassen → atomisch wegschrijven."""
        if self.path is None:
            yield self._mem
            return
        lock_path = self.path.with_suffix(".lock")
        fd = os.open(lock_path, os.O_RDWR | os.O_CREAT, 0o600)
        try:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_EX)
            data = self._read()
            before = json.dumps(data, sort_keys=True)
            yield data
            if json.dumps(data, sort_keys=True) != before:
                self._write(data)
        finally:
            if fcntl is not None:
                fcntl.flock(fd, fcntl.LOCK_UN)
            os.close(fd)

    def _read(self) -> dict:
        assert self.path is not None
        if not self.path.exists():
            return {"version": 1, "days": {}}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict) or not isinstance(data.get("days"), dict):
                raise ValueError("onverwachte structuur")
            return data
        except (ValueError, OSError) as exc:
            # Fail closed: nooit stil terug naar 0.
            raise YukiError(f"Yuki-tellerbestand {self.path} is onleesbaar ({exc}); "
                            "geen call verstuurd. Herstel of verwijder het bestand bewust.") from exc

    def _write(self, data: dict) -> None:
        assert self.path is not None
        days = sorted(data["days"])
        for old in days[:-KEEP_DAYS]:
            data["days"].pop(old, None)
        fd, tmp = tempfile.mkstemp(dir=self.path.parent, prefix=".counter-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh, indent=1, sort_keys=True)
            os.chmod(tmp, 0o600)
            os.replace(tmp, self.path)
        except BaseException:
            with contextlib.suppress(OSError):
                os.unlink(tmp)
            raise

    def _status_from(self, data: dict, domain: str, day: str) -> QuotaStatus:
        rec = data["days"].get(day, {}).get(domain, {})
        return QuotaStatus(domain, day, int(rec.get("calls", 0)), int(rec.get("authenticates", 0)),
                           self.limit, self.warn_at, int(rec.get("blocked", 0)),
                           list(rec.get("open_requests", [])))

    # ----------------------------------------------------------------- API
    def reserve(self, domain: str, *, method: str, authenticate: bool = False,
                administration_id: Optional[str] = None, requested_by: Optional[str] = None) -> QuotaStatus:
        """Reserveer één call vóór verzending. Gooit ``YukiDailyLimitReached`` bij de limiet."""
        if not domain:
            raise YukiConfigError("Geen Yuki-domein om de call op te tellen")
        day = self.today()
        with self._locked() as data:
            rec = data["days"].setdefault(day, {}).setdefault(
                domain, {"calls": 0, "authenticates": 0, "blocked": 0})
            if int(rec.get("calls", 0)) >= self.limit:
                rec["blocked"] = int(rec.get("blocked", 0)) + 1
                pending = rec.setdefault("open_requests", [])
                if len(pending) < MAX_BLOCKED_LOGGED:
                    pending.append({"time": self._clock().astimezone(TZ).isoformat(timespec="seconds"),
                                    "method": method, "administration_id": administration_id,
                                    "requested_by": requested_by})
                status = self._status_from(data, domain, day)
                blocked_exc = YukiDailyLimitReached(status.to_dict())
            else:
                rec["calls"] = int(rec.get("calls", 0)) + 1
                if authenticate:
                    rec["authenticates"] = int(rec.get("authenticates", 0)) + 1
                status = self._status_from(data, domain, day)
                blocked_exc = None
        if blocked_exc is not None:
            log.error("Yuki-daglimiet bereikt voor domein %s (%s/%s); %s niet verstuurd",
                      domain, status.calls, self.limit, method)
            raise blocked_exc
        if status.calls == self.warn_at:
            log.warning("Yuki: %s van %s calls vandaag voor domein %s (80 %%-drempel)",
                        status.calls, self.limit, domain)
        return status

    def status(self, domain: str) -> QuotaStatus:
        day = self.today()
        with self._locked() as data:
            return self._status_from(data, domain, day)

    def all_today(self) -> list[QuotaStatus]:
        day = self.today()
        with self._locked() as data:
            return [self._status_from(data, d, day) for d in sorted(data["days"].get(day, {}))]
