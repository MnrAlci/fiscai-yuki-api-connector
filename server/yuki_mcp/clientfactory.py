"""Bouwt YukiClient-objecten voor de plugin (portaal- of domeinniveau, optioneel per domein een sleutel)."""
from __future__ import annotations

import os
import re
import threading
from pathlib import Path
from typing import Callable, Optional

from yuki_core.cache import SessionCache, fernet_from_secret
from yuki_core.client import SessionManager, YukiClient
from yuki_core.errors import YukiConfigError
from yuki_core.paths import default_data_dir, secure_dir
from yuki_core.quota import DailyQuota
from yuki_core.response_cache import ResponseCache
from yuki_core.soap import DEFAULT_API_BASE

from .limits import LimitConfig, resolve_limit
from .transport import PluginTransport

LEVELS = {"portaal": "portal", "portal": "portal", "domein": "domain", "domain": "domain"}


class PluginQuota(DailyQuota):
    """DailyQuota met de plugin-limietregels (instelbaar tot 1000; daarboven alleen met akkoord)."""

    def __init__(self, data_dir, cfg: LimitConfig, **kw) -> None:
        super().__init__(data_dir, limit=1, warn_at=1, **kw)   # kernvalidatie omzeild met neutrale waarden
        self.limit = cfg.limit
        self.warn_at = cfg.warn_at


def access_level(env=None) -> str:
    env = os.environ if env is None else env
    raw = str(env.get("YUKI_ACCESS_LEVEL", "portaal")).strip().lower() or "portaal"
    if raw not in LEVELS:
        raise YukiConfigError("YUKI_ACCESS_LEVEL moet 'portaal' of 'domein' zijn")
    return LEVELS[raw]


def key_env_name(domein: Optional[str]) -> str:
    if not domein:
        return "YUKI_ACCESS_KEY"
    return "YUKI_ACCESS_KEY_" + re.sub(r"[^A-Z0-9]+", "_", domein.upper()).strip("_")


def _local_cache_key(ddir: Path) -> str:
    """Cachesleutel: uit de omgeving, anders eenmalig lokaal aangemaakt (0600) in de datamap."""
    import secrets
    p = ddir / "cache.key"
    if p.exists():
        return p.read_text(encoding="utf-8").strip()
    val = secrets.token_urlsafe(48)
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(val)
    return val


class ClientFactory:
    def __init__(self, transport_factory: Optional[Callable[[], PluginTransport]] = None,
                 response_cache_factory: Optional[Callable[[], Optional[ResponseCache]]] = None) -> None:
        self._clients: dict[str, YukiClient] = {}
        self._lock = threading.Lock()
        self._transport_factory = transport_factory
        self._rc_factory = response_cache_factory
        self.limits = resolve_limit()
        self.level = access_level()

    def quota(self) -> PluginQuota:
        return PluginQuota(secure_dir(default_data_dir()), self.limits)

    def get(self, domein: Optional[str] = None) -> YukiClient:
        label = (domein or "").strip().lower()
        with self._lock:
            if label in self._clients:
                return self._clients[label]
            env_name = key_env_name(domein)
            access_key = (os.environ.get(env_name, "") or os.environ.get("YUKI_ACCESS_KEY", "")
                          or os.environ.get("YUKI_API_KEY", ""))
            if not access_key:
                raise YukiConfigError(f"Zet {env_name} of YUKI_ACCESS_KEY (alias YUKI_API_KEY) in de omgeving")
            ddir = secure_dir(default_data_dir())
            secret = os.environ.get("YUKI_CACHE_KEY", "") or _local_cache_key(ddir)
            cache = SessionCache(ddir / "sessions.db", fernet_from_secret(secret))
            transport = (self._transport_factory() if self._transport_factory
                         else PluginTransport(os.environ.get("YUKI_API_BASE", DEFAULT_API_BASE)))
            if self._rc_factory:
                rc = self._rc_factory()
            else:
                off = os.environ.get("YUKI_RESPONSE_CACHE", "").strip().lower() in ("off", "0", "uit")
                rc = None if off else ResponseCache()
            sm = SessionManager(access_key, cache, transport, scope=self.level,
                                quota=PluginQuota(ddir, self.limits), response_cache=rc,
                                domain=(domein or None))
            c = YukiClient(sm)
            self._clients[label] = c
            return c
