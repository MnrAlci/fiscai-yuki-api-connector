"""SessionManager, YukiClient en DossierHandle (read-only)."""

from __future__ import annotations

import contextlib
import logging
import os
import re
import threading
from datetime import date, datetime
from pathlib import Path
from typing import Any, Iterator, Optional, Sequence
from xml.etree import ElementTree as ET

from . import models
from .cache import CachedSession, Clock, SessionCache, fingerprint, session_ttl_from_env, utcnow
from .errors import (YukiAmbiguousDossier, YukiConfigError, YukiDossierNotFound,
                     YukiError, YukiSoapFault)
from .quota import DailyQuota
from .response_cache import NEVER_CACHE, ResponseCache, cache_key, default_ttl
from .soap import DEFAULT_API_BASE, Param, SoapTransport

try:  # cross-process single-flight (POSIX)
    import fcntl  # type: ignore
except ImportError:  # pragma: no cover - Windows
    fcntl = None  # type: ignore

log = logging.getLogger("yuki_core.client")

FREE_CALLS_PER_DAY = 1000   # gratis staffel van Yuki (per domein per dag)
# Harde limiet en waarschuwing: zie quota.DEFAULT_LIMIT (900) / DEFAULT_WARN (720).
GUID_RE = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")

# Authenticate bestaat op beide services; de sessie is service-overschrijdend.
AUTH_SERVICE = "Accounting"


class SessionManager:
    """Beheert één Yuki-sessie per (access key, scope).

    - ``get_session()`` geeft een geldige sessie; ``Authenticate`` enkel bij
      cache-miss of verval (TTL 23u).
    - Single-flight: een thread-lock plus (POSIX) een bestandslock naast de
      SQLite-db, zodat parallelle aanvragen niet allemaal inloggen.
    - ``call()`` voert een SOAP-call uit met de sessie en doet bij een
      'invalid session'-fault precies één keer: cache wissen → opnieuw
      authenticeren → call herhalen.
    - Elke echte call (ook ``Authenticate`` en de herhaling) wordt vóór
      verzending gereserveerd in de ``DailyQuota`` (per domein, per dag
      Europe/Brussels; standaard limiet 900). Er is altijd een teller: zonder
      expliciete ``quota`` komt hij naast de sessie-db (of in het geheugen).
    - Met een ``ResponseCache`` worden leesresultaten gedeeld; een hit
      verstuurt niets en telt niet mee.
    """

    def __init__(self, access_key: str, cache: SessionCache, transport: SoapTransport,
                 scope: str = "portal", clock: Clock = utcnow, *,
                 quota: Optional[DailyQuota] = None,
                 response_cache: Optional[ResponseCache] = None,
                 domain: Optional[str] = None,
                 requested_by: Optional[str] = None) -> None:
        if not access_key:
            raise YukiConfigError("YUKI_ACCESS_KEY ontbreekt")
        if scope not in ("portal", "domain"):
            raise YukiConfigError("scope moet 'portal' of 'domain' zijn")
        self._access_key = access_key
        self.key_fp = fingerprint(access_key)
        self.scope = scope
        self.cache = cache
        self.transport = transport
        self._clock = clock
        self._lock = threading.Lock()
        if quota is None:
            quota = (DailyQuota(cache.db_path.parent, clock=clock) if cache.db_path is not None
                     else DailyQuota(persistent=False, clock=clock))
        self.quota = quota
        self.response_cache = response_cache
        # Domein voor portaal-calls (Authenticate, Administrations) en voor
        # administraties zonder DomainID. Aanname: die calls tellen op het
        # domein van de sleutel; zet YUKI_DOMAIN om het expliciet te benoemen.
        self.default_domain = (domain or os.environ.get("YUKI_DOMAIN", "").strip()
                               or f"sleutel-{self.key_fp[:10]}")
        self.requested_by = requested_by or os.environ.get("YUKI_REQUESTED_BY", "").strip() or None

    def __repr__(self) -> str:
        return f"SessionManager(key={self.key_fp[:10]}, scope={self.scope})"

    # -------------------------------------------------------------- session
    def get_session(self) -> CachedSession:
        hit = self.cache.get(self.key_fp, self.scope)
        if hit is not None:
            return hit
        with self._lock, self._file_lock():
            hit = self.cache.get(self.key_fp, self.scope)  # double-checked
            if hit is not None:
                return hit
            return self._authenticate()

    def _authenticate(self) -> CachedSession:
        self._count("Authenticate", authenticate=True)
        result = self.transport.call(AUTH_SERVICE, "Authenticate", [("accessKey", self._access_key)])
        session_id = (result.text or "").strip() if result is not None else ""
        if not session_id:
            raise YukiError("Authenticate gaf geen session ID terug (ongeldige access key of rechten?)")
        sess = self.cache.put(self.key_fp, self.scope, session_id, session_ttl_from_env())
        log.info("Yuki-sessie aangemaakt voor key %s (%s), geldig tot %s",
                 self.key_fp[:10], self.scope, sess.expires_at.isoformat())
        return sess

    def invalidate(self) -> None:
        self.cache.delete(self.key_fp, self.scope)

    @contextlib.contextmanager
    def _file_lock(self) -> Iterator[None]:
        db = self.cache.db_path
        if fcntl is None or db is None:
            yield
            return
        lock_path = Path(f"{db}.{self.key_fp[:16]}.{self.scope}.lock")
        with open(lock_path, "a+") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)

    # ----------------------------------------------------------------- call
    def _count(self, method: str, authenticate: bool = False, domain: Optional[str] = None,
               administration_id: Optional[str] = None) -> None:
        """Reserveer één call; gooit ``YukiDailyLimitReached`` (niets verstuurd)."""
        self.quota.reserve(domain or self.default_domain, method=method, authenticate=authenticate,
                           administration_id=administration_id, requested_by=self.requested_by)

    @property
    def calls_today(self) -> int:
        return self.quota.status(self.default_domain).calls

    def call(self, service: str, method: str, params: Sequence[Param], *,
             administration_id: Optional[str] = None, domain: Optional[str] = None,
             force_refresh: bool = False, cache_ttl=None) -> Optional[ET.Element]:
        """SOAP-call met ``sessionID`` als eerste parameter (zoals in de WSDL).

        Volgorde: antwoordcache (tenzij ``force_refresh``) → dagteller → call.
        """
        dom = domain or self.default_domain
        rc = self.response_cache if method not in NEVER_CACHE else None
        key = None
        if rc is not None:
            key = cache_key(dom, administration_id, service, method, params)
            if not force_refresh:
                hit = rc.get(key)
                if hit is not None:
                    log.debug("cache-hit %s.%s", service, method)
                    return hit.result
        sess = self.get_session()
        try:
            self._count(method, domain=dom, administration_id=administration_id)
            result = self.transport.call(service, method, [("sessionID", sess.session_id), *params])
        except YukiSoapFault as fault:
            if not fault.is_invalid_session:
                raise
            log.info("Sessie ongeldig volgens Yuki (%s); één keer opnieuw authenticeren", method)
            with self._lock, self._file_lock():
                current = self.cache.get(self.key_fp, self.scope)
                if current is None or current.session_id == sess.session_id:
                    self.cache.delete(self.key_fp, self.scope)
                    current = self._authenticate()
            self._count(method, domain=dom, administration_id=administration_id)
            result = self.transport.call(service, method, [("sessionID", current.session_id), *params])
        self.cache.touch(self.key_fp, self.scope)
        if rc is not None and key is not None:
            ttl = cache_ttl or default_ttl(method, params, self._clock())
            rc.put(key, domain=dom, administration_id=administration_id, service=service,
                   method=method, result=result, ttl=ttl)
        return result


class YukiClient:
    """Portaalniveau: administraties oplijsten en dossiers openen."""

    def __init__(self, sessions: SessionManager) -> None:
        self.sessions = sessions
        self._admins: Optional[list[models.Administration]] = None

    @classmethod
    def from_env(cls, *, data_dir: Optional[Path | str] = None, scope: Optional[str] = None,
                 transport: Optional[SoapTransport] = None, clock: Clock = utcnow) -> "YukiClient":
        """Bouw een client uit ``YUKI_ACCESS_KEY``, ``YUKI_CACHE_KEY``, ``YUKI_API_BASE``,
        ``YUKI_DATA_DIR``, ``YUKI_SCOPE`` (portal|domain), ``YUKI_DOMAIN``,
        ``YUKI_RESPONSE_CACHE_DIR`` en ``YUKI_RESPONSE_CACHE`` (``off`` = uit)."""
        from .cache import fernet_from_secret
        from .paths import default_data_dir, secure_dir

        access_key = os.environ.get("YUKI_ACCESS_KEY", "")
        if not access_key:
            raise YukiConfigError("Zet YUKI_ACCESS_KEY (Yuki WebserviceAccessKey) in de omgeving")
        cache_secret = os.environ.get("YUKI_CACHE_KEY", "")
        if not cache_secret:
            raise YukiConfigError("Zet YUKI_CACHE_KEY (Fernet-sleutel of sterk geheim) in de omgeving")
        ddir = secure_dir(Path(data_dir) if data_dir else default_data_dir())
        cache = SessionCache(ddir / "sessions.db", fernet_from_secret(cache_secret), clock=clock)
        transport = transport or SoapTransport(os.environ.get("YUKI_API_BASE", DEFAULT_API_BASE))
        rc = (None if os.environ.get("YUKI_RESPONSE_CACHE", "").strip().lower() in ("off", "0", "uit")
              else ResponseCache(clock=clock))
        sm = SessionManager(access_key, cache, transport,
                            scope=scope or os.environ.get("YUKI_SCOPE", "portal"), clock=clock,
                            quota=DailyQuota(ddir, clock=clock), response_cache=rc)
        return cls(sm)

    # --------------------------------------------------------- dossiers
    def list_administrations(self, with_internal_code: bool = False,
                             refresh: bool = False) -> list[models.Administration]:
        """AccountingInfo.Administrations — live bevestigd op 6 mei 2026.
        AdministrationsWithInternalCustomerCode bestaat op beide services, maar
        is nog niet live aangeroepen.
        """
        if with_internal_code:
            res = self.sessions.call("AccountingInfo", "AdministrationsWithInternalCustomerCode", [],
                                     force_refresh=refresh)
            return models.parse_administrations(res)
        if self._admins is None or refresh:
            res = self.sessions.call("AccountingInfo", "Administrations", [], force_refresh=refresh)
            self._admins = models.parse_administrations(res)
        return list(self._admins)

    def resolve(self, naam_of_id: str) -> models.Administration:
        """Zoek een administratie op Administration ID (GUID) of naam."""
        q = (naam_of_id or "").strip()
        if not q:
            raise YukiDossierNotFound("Lege dossiernaam/ID")
        admins = self.list_administrations()
        if GUID_RE.match(q):
            for a in admins:
                if a.id.lower() == q.lower():
                    return a
            raise YukiDossierNotFound(f"Administration ID {q} niet gevonden voor deze sleutel")
        exact = [a for a in admins if a.name.casefold() == q.casefold()]
        if len(exact) == 1:
            return exact[0]
        partial = exact or [a for a in admins if q.casefold() in a.name.casefold()]
        if len(partial) == 1:
            return partial[0]
        if not partial:
            raise YukiDossierNotFound(f"Geen administratie gevonden voor '{q}'")
        raise YukiAmbiguousDossier(q, partial)

    def open_dossier(self, naam_of_id: str) -> "DossierHandle":
        return DossierHandle(self, self.resolve(naam_of_id))


def _as_dt(value: date | datetime | str) -> datetime:
    if isinstance(value, datetime):
        return value
    if isinstance(value, date):
        return datetime(value.year, value.month, value.day)
    return datetime.fromisoformat(value)


class DossierHandle:
    """Tijdelijke, scoped verbinding voor één administratie.

    ``close()`` gooit alleen de handle en opgehaalde data weg; de gedeelde
    24u-sessie blijft in de cache.
    """

    def __init__(self, client: YukiClient, admin: models.Administration) -> None:
        self._client: Optional[YukiClient] = client
        self.administration = admin
        self.fetched: dict[str, Any] = {}
        self.force_refresh = False   # True → antwoordcache overslaan voor deze handle

    @property
    def closed(self) -> bool:
        return self._client is None

    def _call(self, service: str, method: str, params: Sequence[Param],
              force_refresh: bool = False) -> Optional[ET.Element]:
        if self._client is None:
            raise YukiError("Dossierhandle is gesloten")
        return self._client.sessions.call(
            service, method, [("administrationID", self.administration.id), *params],
            administration_id=self.administration.id, domain=self.administration.domain_id,
            force_refresh=force_refresh or self.force_refresh)

    # ------------------------------------------------------- Accounting
    def trial_balance(self, datum: date | datetime | str, fiscaal: bool = False,
                      year_end: bool = False) -> list[models.GLLine]:
        """GLAccountBalance / GLAccountBalanceFiscal / GLAccountBalanceYearEnd(transactionDate)."""
        method = ("GLAccountBalanceYearEnd" if year_end
                  else "GLAccountBalanceFiscal" if fiscaal else "GLAccountBalance")
        lines = models.parse_gl_balance(self._call("Accounting", method, [("transactionDate", _as_dt(datum))]))
        self.fetched[method] = lines
        return lines

    def net_revenue(self, van: date | datetime | str, tot: date | datetime | str,
                    fiscaal: bool = False) -> models.NetRevenue:
        """NetRevenue / NetRevenueFiscal(StartDate, EndDate) → decimal."""
        method = "NetRevenueFiscal" if fiscaal else "NetRevenue"
        v, t = _as_dt(van), _as_dt(tot)
        res = self._call("Accounting", method, [("StartDate", v), ("EndDate", t)])
        out = models.NetRevenue(v, t, fiscaal, models.parse_decimal_result(res))
        self.fetched[method] = out
        return out

    def open_items(self, soort: str, peildatum: Optional[date | datetime | str] = None,
                   include_bank_transactions: bool = False,
                   sort_order: str = "DateAsc") -> list[models.OpenItem]:
        """Outstanding{Debtor|Creditor}Items, of ...ByDateOutstanding(dateOutstanding) met peildatum."""
        kind = {"debiteuren": "Debtor", "klanten": "Debtor",
                "crediteuren": "Creditor", "leveranciers": "Creditor"}.get(soort.lower())
        if kind is None:
            raise ValueError("soort moet 'debiteuren' of 'crediteuren' zijn")
        if sort_order not in ("ContactAsc", "ContactDesc", "AmountAsc", "AmountDesc", "DateAsc", "DateDesc"):
            raise ValueError("ongeldige sort_order")
        params: list[Param] = [("includeBankTransactions", include_bank_transactions),
                               ("sortOrder", sort_order)]
        method = f"Outstanding{kind}Items"
        if peildatum is not None:
            method += "ByDateOutstanding"
            params.append(("dateOutstanding", _as_dt(peildatum)))
        items = models.parse_open_items(self._call("Accounting", method, params))
        self.fetched[method] = items
        return items

    # --------------------------------------------------- AccountingInfo
    def gl_transactions(self, rekening: str, van: date | datetime | str, tot: date | datetime | str,
                        fiscaal: bool = False) -> list[models.Transaction]:
        """AccountingInfo.GetTransactionDetails(GLAccountCode, StartDate, EndDate, financialMode)."""
        res = self._call("AccountingInfo", "GetTransactionDetails", [
            ("GLAccountCode", rekening), ("StartDate", _as_dt(van)), ("EndDate", _as_dt(tot)),
            ("financialMode", 1 if fiscaal else 0)])
        txs = models.parse_transaction_details(res)
        self.fetched[f"GetTransactionDetails:{rekening}"] = txs
        return txs

    def gl_account_scheme(self) -> list[models.GLLine]:
        """AccountingInfo.GetGLAccountScheme."""
        scheme = models.parse_gl_scheme(self._call("AccountingInfo", "GetGLAccountScheme", []))
        self.fetched["GetGLAccountScheme"] = scheme
        return scheme

    def financial_year_modified(self, year_id: int) -> Optional[datetime]:
        """AccountingInfo.GetFinancialYearModifiedDate(yearID) – om te zien of herophalen nodig is."""
        res = self._call("AccountingInfo", "GetFinancialYearModifiedDate", [("yearID", year_id)])
        return models.to_datetime((res.text or "").strip() if res is not None else None)

    # ------------------------------------------------------------ close
    def close(self) -> None:
        """Handle + opgehaalde data vrijgeven. De gecachete sessie blijft."""
        self.fetched.clear()
        self._client = None

    def __enter__(self) -> "DossierHandle":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()
