"""Standaardpaden: alles onder de eigen gebruikersmap (geen gedeelde map, geen centrale opslag).

Overschrijfbaar met ``YUKI_DATA_DIR`` (sessies + teller) en ``YUKI_RESPONSE_CACHE_DIR``.
"""

from __future__ import annotations

import os
from pathlib import Path

HOME_DIR = Path.home() / ".fiscai-yuki-api-connector"


def secure_dir(path: Path | str) -> Path:
    """Maak ``path`` aan (0700) en geef het terug."""
    p = Path(path).expanduser()
    p.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(p, 0o700)
    except OSError:
        pass
    return p


def default_data_dir() -> Path:
    env = os.environ.get("YUKI_DATA_DIR", "").strip()
    return Path(env).expanduser() if env else HOME_DIR


def default_response_cache_dir() -> Path:
    env = os.environ.get("YUKI_RESPONSE_CACHE_DIR", "").strip()
    return Path(env).expanduser() if env else HOME_DIR / "cache"
