"""Configuratie: voorrang CLI > omgeving > bestand (.env of config). Geheimen staan nooit in het configbestand."""
from __future__ import annotations

import json
import os
import re
from pathlib import Path
from typing import Optional

# Niet-geheime sleutels die een configbestand mag zetten, en de omgevingsvariabele waarop ze landen.
ALLOWED = {"access_level": "YUKI_ACCESS_LEVEL", "daily_limit": "YUKI_DAILY_LIMIT", "daily_warn": "YUKI_DAILY_WARN", "data_dir": "YUKI_DATA_DIR",
           "response_cache": "YUKI_RESPONSE_CACHE", "max_retries": "YUKI_MAX_RETRIES", "log_level": "YUKI_LOG_LEVEL", "log_format": "YUKI_LOG_FORMAT",
           "hooks_file": "YUKI_HOOKS_FILE"}
SECRET_WORDS = re.compile(r"(key|secret|token|password|passwd)", re.I)
# Een profiel mag verwijzen naar de NAAM van een omgevingsvariabele met de sleutel (key_env), nooit naar de waarde.
EXTRA = {"administratie", "key_env"}
ENV_NAME = re.compile(r"^[A-Z][A-Z0-9_]*$")


class ConfigError(Exception):
    pass


UNRESOLVED = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*\}$")


def drop_unresolved_placeholders(environ=None) -> list[str]:
    """Verwijder YUKI_*-variabelen met een niet-ingevulde plaatshouder zoals '${YUKI_DOMAIN}'.

    Sommige MCP-clients vullen ``${VAR}`` in mcp.json niet in en geven de tekst letterlijk door.
    Zo'n waarde telt als 'niet ingesteld', zodat de standaardwaarde geldt (schrijven blijft dus uit).
    """
    environ = os.environ if environ is None else environ
    weg = [k for k, v in list(environ.items()) if k.startswith("YUKI_") and UNRESOLVED.match(str(v).strip())]
    for k in weg:
        del environ[k]
    return weg


def parse_env_file(text: str) -> dict:
    out = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        if line.startswith("export "):
            line = line[7:]
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
            v = v[1:-1]
        if ENV_NAME.match(k):
            out[k] = v
    return out


def apply_env_file(path: Path, environ=None) -> list[str]:
    """Zet waarden uit een .env-bestand alleen als de omgeving ze nog niet heeft (omgeving wint). Geeft de gezette namen terug (zonder waarden)."""
    environ = os.environ if environ is None else environ
    set_ = []
    for k, v in parse_env_file(Path(path).read_text(encoding="utf-8")).items():
        if k not in environ:
            environ[k] = v
            set_.append(k)
    return set_


def _load_struct(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import tomllib
    except ImportError:  # Python 3.10
        try:
            import tomli as tomllib  # type: ignore
        except ImportError as exc:
            raise ConfigError("TOML lezen vraagt Python 3.11+ of het pakket 'tomli'; gebruik anders een .json-bestand.") from exc
    return tomllib.loads(text)


def load_config(path: Optional[Path], profile: Optional[str] = None) -> dict:
    """Leest [default] en optioneel [profiles.<naam>]; weigert geheimen. Geeft een dict met alleen toegelaten sleutels."""
    if path is None:
        return {}
    data = _load_struct(Path(path))
    merged = dict(data.get("default", {}))
    if profile:
        prof = (data.get("profiles") or {}).get(profile)
        if prof is None:
            raise ConfigError(f"Profiel '{profile}' niet gevonden in {path}.")
        merged.update(prof)
    for k, v in merged.items():
        if k == "key_env":
            if not isinstance(v, str) or not ENV_NAME.match(v):
                raise ConfigError("key_env moet de NAAM van een omgevingsvariabele zijn (bv. YUKI_ACCESS_KEY_KLANT_A).")
            continue
        if k not in ALLOWED and k not in EXTRA:
            if SECRET_WORDS.search(k):
                raise ConfigError(f"'{k}' lijkt een geheim: zet sleutels nooit in een configbestand (gebruik de omgeving of key_env).")
            raise ConfigError(f"Onbekende configsleutel '{k}'. Toegelaten: {', '.join(sorted(set(ALLOWED) | EXTRA))}.")
    return merged


def apply_config(cfg: dict, environ=None) -> None:
    environ = os.environ if environ is None else environ
    for k, v in cfg.items():
        if k in ALLOWED:
            environ.setdefault(ALLOWED[k], str(v))
    ke = cfg.get("key_env")
    if ke and ke in environ and "YUKI_ACCESS_KEY" not in environ:
        environ["YUKI_ACCESS_KEY"] = environ[ke]


ENV_TEMPLATE = """# FISCAi Yuki API Connector: example environment file (placeholders only).
# Copy to .env, fill in your own values, and NEVER commit it. Real environment variables win over this file.
YUKI_ACCESS_KEY=
# portaal (all administrations) or domein (one domain)
YUKI_ACCESS_LEVEL=portaal
# Safety: daily Yuki call limit (default 900)
# YUKI_DAILY_LIMIT=900
# Optional automatic retry for network errors (default 0 = off, maximum 5)
# YUKI_MAX_RETRIES=0
# Logging: debug|info|warning|error, text|json (logs never contain keys or tool arguments)
# YUKI_LOG_LEVEL=warning
# YUKI_LOG_FORMAT=text
# Hooks are OFF unless you point to a hooks file (see docs/HOOKS.md)
# YUKI_HOOKS_FILE=hooks.toml
# Writing to Yuki is OFF by default. Do not enable it unless you have read docs/BOEKINGSWORKFLOW.md.
"""
