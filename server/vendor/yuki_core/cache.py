"""Versleutelde sessiecache (SQLite + geheugen) voor Yuki-sessies.

- Sleutel: SHA-256-vingerafdruk van de access key + scope ("portal"/"domain").
  De ruwe access key wordt nooit opgeslagen.
- ``session_id`` staat Fernet-versleuteld op schijf; de cache key komt uit
  ``YUKI_CACHE_KEY`` (een Fernet-sleutel, of een willekeurig geheim waaruit
  via HKDF-SHA256 een sleutel wordt afgeleid).
- De oude SQLite-call-teller (``count_call``) blijft alleen voor
  compatibiliteit; de echte, harde dagteller per domein zit sinds 0.2.0 in
  ``quota.DailyQuota`` (JSON + bestandslock, limiet 900).
"""

from __future__ import annotations

import base64
import hashlib
import logging
import os
import sqlite3
import threading
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Optional

from cryptography.fernet import Fernet, InvalidToken
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.hkdf import HKDF

from .errors import YukiConfigError

log = logging.getLogger("yuki_core.cache")

SESSION_TTL = timedelta(hours=23)  # officiële 24u minus 1u marge; niet live bevestigd
_HKDF_SALT = b"yuki-core/session-cache/v1"

Clock = Callable[[], datetime]


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def session_ttl_from_env() -> timedelta:
    """Standaard 23 uur. Overschrijf met YUKI_SESSION_TTL_MINUTES (5–1380).

    De 24-uurs-geldigheid is niet live bevestigd; een eerdere snapshotgenerator
    gebruikte 60 minuten.
    """
    raw = os.environ.get("YUKI_SESSION_TTL_MINUTES", "").strip()
    if not raw:
        return SESSION_TTL
    try:
        minutes = int(raw)
    except ValueError as exc:
        raise YukiConfigError("YUKI_SESSION_TTL_MINUTES moet een geheel aantal minuten zijn") from exc
    if minutes < 5 or minutes > 23 * 60:
        raise YukiConfigError("YUKI_SESSION_TTL_MINUTES moet tussen 5 en 1380 liggen")
    return timedelta(minutes=minutes)


def fingerprint(access_key: str) -> str:
    """Volledige SHA-256-hex van de access key (cache-sleutel)."""
    return hashlib.sha256(access_key.encode("utf-8")).hexdigest()


def short_fp(value: str) -> str:
    """Korte vingerafdruk voor logs (nooit de waarde zelf loggen)."""
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:10]


def fernet_from_secret(secret: str) -> Fernet:
    """Fernet uit ``YUKI_CACHE_KEY``: geldige Fernet-sleutel of afgeleid via HKDF."""
    if not secret:
        raise YukiConfigError("YUKI_CACHE_KEY is leeg")
    try:
        return Fernet(secret.encode("ascii"))
    except (ValueError, UnicodeEncodeError):
        pass
    key = HKDF(algorithm=hashes.SHA256(), length=32, salt=_HKDF_SALT,
               info=b"fernet-key").derive(secret.encode("utf-8"))
    return Fernet(base64.urlsafe_b64encode(key))


def default_data_dir() -> Path:
    from .paths import default_data_dir as _d
    return _d()


@dataclass(frozen=True)
class CachedSession:
    key_fp: str
    scope: str
    session_id: str
    obtained_at: datetime
    expires_at: datetime
    last_used_at: datetime

    def is_valid(self, now: datetime) -> bool:
        return now < self.expires_at

    def __repr__(self) -> str:  # session_id nooit tonen
        return (f"CachedSession(key={self.key_fp[:10]}, scope={self.scope}, "
                f"expires_at={self.expires_at.isoformat()})")


class SessionCache:
    """Geheugencache bovenop een versleutelde SQLite-store."""

    def __init__(self, db_path: Optional[Path | str], fernet: Optional[Fernet],
                 clock: Clock = utcnow) -> None:
        """``db_path=None`` → enkel geheugen (geen persistentie)."""
        self._clock = clock
        self._fernet = fernet
        self._mem: dict[tuple[str, str], CachedSession] = {}
        self._mem_lock = threading.Lock()
        self._mem_counter: dict[tuple[str, str], int] = {}
        self.db_path: Optional[Path] = Path(db_path) if db_path else None
        if self.db_path is not None:
            if fernet is None:
                raise YukiConfigError("Persistente cache vereist een YUKI_CACHE_KEY")
            self.db_path.parent.mkdir(parents=True, exist_ok=True)
            try:
                os.chmod(self.db_path.parent, 0o700)
            except OSError:
                pass
            self._init_db()

    # ------------------------------------------------------------------ db
    def _connect(self) -> sqlite3.Connection:
        assert self.db_path is not None
        conn = sqlite3.connect(self.db_path, timeout=30)
        conn.execute("PRAGMA journal_mode=WAL")
        return conn

    def _init_db(self) -> None:
        with self._connect() as conn:
            conn.execute(
                """CREATE TABLE IF NOT EXISTS sessions (
                    key_fp TEXT NOT NULL,
                    scope TEXT NOT NULL,
                    session_id_enc BLOB NOT NULL,
                    obtained_at TEXT NOT NULL,
                    expires_at TEXT NOT NULL,
                    last_used_at TEXT NOT NULL,
                    PRIMARY KEY (key_fp, scope))"""
            )
            conn.execute(
                """CREATE TABLE IF NOT EXISTS call_counter (
                    key_fp TEXT NOT NULL,
                    day TEXT NOT NULL,
                    calls INTEGER NOT NULL DEFAULT 0,
                    authenticates INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (key_fp, day))"""
            )
        try:
            os.chmod(self.db_path, 0o600)  # type: ignore[arg-type]
        except OSError:
            pass

    # ------------------------------------------------------------- sessions
    def get(self, key_fp: str, scope: str) -> Optional[CachedSession]:
        """Geldige sessie uit geheugen of schijf, anders ``None``."""
        now = self._clock()
        with self._mem_lock:
            hit = self._mem.get((key_fp, scope))
        if hit is not None:
            if hit.is_valid(now):
                return hit
            self.delete(key_fp, scope)
            return None
        if self.db_path is None:
            return None
        with self._connect() as conn:
            row = conn.execute(
                "SELECT session_id_enc, obtained_at, expires_at, last_used_at "
                "FROM sessions WHERE key_fp=? AND scope=?", (key_fp, scope)).fetchone()
        if row is None:
            return None
        try:
            sid = self._fernet.decrypt(row[0]).decode("utf-8")  # type: ignore[union-attr]
        except InvalidToken:
            log.warning("Cache-entry %s/%s niet te ontsleutelen (andere YUKI_CACHE_KEY?); verwijderd",
                        key_fp[:10], scope)
            self.delete(key_fp, scope)
            return None
        sess = CachedSession(key_fp, scope, sid, datetime.fromisoformat(row[1]),
                             datetime.fromisoformat(row[2]), datetime.fromisoformat(row[3]))
        if not sess.is_valid(now):
            self.delete(key_fp, scope)
            return None
        with self._mem_lock:
            self._mem[(key_fp, scope)] = sess
        return sess

    def put(self, key_fp: str, scope: str, session_id: str,
            ttl: timedelta = SESSION_TTL) -> CachedSession:
        now = self._clock()
        sess = CachedSession(key_fp, scope, session_id, now, now + ttl, now)
        with self._mem_lock:
            self._mem[(key_fp, scope)] = sess
        if self.db_path is not None:
            enc = self._fernet.encrypt(session_id.encode("utf-8"))  # type: ignore[union-attr]
            with self._connect() as conn:
                conn.execute(
                    "INSERT OR REPLACE INTO sessions VALUES (?,?,?,?,?,?)",
                    (key_fp, scope, enc, sess.obtained_at.isoformat(),
                     sess.expires_at.isoformat(), sess.last_used_at.isoformat()))
        return sess

    def touch(self, key_fp: str, scope: str) -> None:
        now = self._clock()
        with self._mem_lock:
            cur = self._mem.get((key_fp, scope))
            if cur is not None:
                self._mem[(key_fp, scope)] = replace(cur, last_used_at=now)
        if self.db_path is not None:
            with self._connect() as conn:
                conn.execute("UPDATE sessions SET last_used_at=? WHERE key_fp=? AND scope=?",
                             (now.isoformat(), key_fp, scope))

    def delete(self, key_fp: str, scope: str) -> None:
        with self._mem_lock:
            self._mem.pop((key_fp, scope), None)
        if self.db_path is not None:
            with self._connect() as conn:
                conn.execute("DELETE FROM sessions WHERE key_fp=? AND scope=?", (key_fp, scope))

    def forget_memory(self) -> None:
        """Alleen de geheugenkopie wissen (bv. in tests: simuleer nieuw proces)."""
        with self._mem_lock:
            self._mem.clear()

    # --------------------------------------------------------- call counter
    def count_call(self, key_fp: str, authenticate: bool = False) -> int:
        """Verhoog de dagteller (UTC-dag) en geef het totaal van vandaag terug."""
        day = self._clock().date().isoformat()
        if self.db_path is None:
            k = (key_fp, day)
            with self._mem_lock:
                self._mem_counter[k] = self._mem_counter.get(k, 0) + 1
                return self._mem_counter[k]
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO call_counter (key_fp, day, calls, authenticates) VALUES (?,?,1,?) "
                "ON CONFLICT(key_fp, day) DO UPDATE SET calls=calls+1, "
                "authenticates=authenticates+excluded.authenticates",
                (key_fp, day, 1 if authenticate else 0))
            return conn.execute("SELECT calls FROM call_counter WHERE key_fp=? AND day=?",
                                (key_fp, day)).fetchone()[0]

    def calls_today(self, key_fp: str) -> int:
        day = self._clock().date().isoformat()
        if self.db_path is None:
            return self._mem_counter.get((key_fp, day), 0)
        with self._connect() as conn:
            row = conn.execute("SELECT calls FROM call_counter WHERE key_fp=? AND day=?",
                               (key_fp, day)).fetchone()
        return row[0] if row else 0
