"""Hooks (standaard UIT): pre_call, post_call, on_error, on_export. Lokale scripts of Python-functies; ze krijgen nooit geheimen.

Configuratie (TOML of JSON) via ``--hooks FILE`` of ``YUKI_HOOKS_FILE``. Zonder ``enabled = true`` gebeurt er niets.
Een hook mislukt nooit de toolaanroep: fouten worden gelogd en genegeerd.
"""
from __future__ import annotations

import importlib
import json
import logging
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Optional

from .convert import scrub

LOG = logging.getLogger("yuki.hooks")
EVENTS = ("pre_call", "post_call", "on_error", "on_export")
SECRET_KEYS = re.compile(r"(key|secret|token|password|passwd|authorization|credential)", re.I)
SAFE_ENV = ("PATH", "HOME", "USERPROFILE", "SYSTEMROOT", "LANG", "LC_ALL", "TMPDIR", "TEMP", "TMP")


def sanitize(value: Any) -> Any:
    """Verwijdert geheim-achtige sleutels en scrubt de rest."""
    if isinstance(value, dict):
        return {k: ("[verborgen]" if SECRET_KEYS.search(str(k)) else sanitize(v)) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [sanitize(v) for v in value]
    return scrub(value)


def _load(path: Path) -> dict:
    text = path.read_text(encoding="utf-8")
    if path.suffix.lower() == ".json":
        return json.loads(text)
    try:
        import tomllib
    except ImportError:
        import tomli as tomllib  # type: ignore
    return tomllib.loads(text)


class Hooks:
    def __init__(self, cfg: dict | None = None, base: Path | None = None) -> None:
        cfg = cfg or {}
        self.enabled = bool(cfg.get("enabled", False))
        self.timeout = float(cfg.get("timeout_seconds", 10))
        self.base = Path(base or ".").resolve()
        self.hooks = [h for h in cfg.get("hooks", []) if h.get("event") in EVENTS] if self.enabled else []
        for h in cfg.get("hooks", []):
            if h.get("event") not in EVENTS:
                raise ValueError(f"Onbekend hook-event '{h.get('event')}'. Kies uit: {', '.join(EVENTS)}.")
            if bool(h.get("command")) == bool(h.get("python")):
                raise ValueError("Elke hook heeft precies één van 'command' (lijst) of 'python' (module:functie).")
            if h.get("command") and not isinstance(h["command"], list):
                raise ValueError("'command' moet een lijst zijn (geen shell-tekst).")

    @classmethod
    def load(cls, path: Optional[str | Path]) -> "Hooks":
        if not path:
            return cls()
        p = Path(path).expanduser()
        return cls(_load(p), p.parent)

    @classmethod
    def from_env(cls) -> "Hooks":
        return cls.load(os.environ.get("YUKI_HOOKS_FILE") or None)

    def fire(self, event: str, payload: dict) -> list[dict]:
        out = []
        if not self.enabled:
            return out
        body = {"event": event, "time": datetime.now(timezone.utc).isoformat(timespec="seconds"), **sanitize(payload)}
        for h in self.hooks:
            if h["event"] != event or (h.get("tools") and payload.get("tool") not in h["tools"]):
                continue
            t0 = time.time()
            try:
                if h.get("command"):
                    self._run_command(h["command"], body, event)
                else:
                    self._run_python(h["python"], body)
                out.append({"hook": h.get("name") or h.get("command") or h.get("python"), "ok": True})
            except Exception as exc:  # noqa: BLE001 - hooks mogen de aanroep nooit breken
                LOG.warning("hook mislukt: %s", f"{type(exc).__name__}: {exc}", extra={"event": event, "ok": False})
                out.append({"hook": h.get("name") or str(h.get("command") or h.get("python")), "ok": False, "error": type(exc).__name__})
            LOG.debug("hook klaar", extra={"event": event, "duration_ms": int((time.time() - t0) * 1000)})
        return out

    def _run_command(self, command: list, body: dict, event: str) -> None:
        env = {k: os.environ[k] for k in SAFE_ENV if k in os.environ}
        env.update({"YUKI_HOOK_EVENT": event, "YUKI_HOOK_TOOL": str(body.get("tool", ""))})
        subprocess.run([str(c) for c in command], input=json.dumps(body, ensure_ascii=False, default=str), text=True, env=env, cwd=self.base,
                       timeout=self.timeout, check=True, capture_output=True, shell=False)

    def _run_python(self, spec: str, body: dict) -> None:
        mod, _, fn = spec.partition(":")
        if not mod or not fn:
            raise ValueError("python-hook moet 'module:functie' zijn")
        if str(self.base) not in sys.path:
            sys.path.insert(0, str(self.base))
        getattr(importlib.import_module(mod), fn)(body)


def guarded_call(hooks: Hooks, call: Callable[[str, Optional[dict]], dict], name: str, args: Optional[dict]) -> dict:
    """Roept ``call`` aan en vuurt de hooks af; fouten worden doorgegeven na on_error."""
    base = {"tool": name, "args": args or {}}
    hooks.fire("pre_call", base)
    t0 = time.time()
    try:
        res = call(name, args)
    except Exception as exc:
        hooks.fire("on_error", {**base, "error": f"{type(exc).__name__}: {scrub(str(exc))}", "duration_ms": int((time.time() - t0) * 1000)})
        raise
    summary = {"keys": sorted(res)[:20] if isinstance(res, dict) else None, "bytes": len(json.dumps(res, default=str))}
    hooks.fire("post_call", {**base, "ok": True, "result_summary": summary, "duration_ms": int((time.time() - t0) * 1000)})
    if name == "yuki_export_dataset" and isinstance(res, dict) and res.get("bestanden"):
        hooks.fire("on_export", {**base, "files": res["bestanden"], "export_dir": (args or {}).get("export_map")})
    if name == "yuki_dossier_transfer_export" and isinstance(res, dict) and res.get("status") in ("klaar", "onderbroken"):
        hooks.fire("on_export", {**base, "files": [], "export_dir": res.get("export_map") or (args or {}).get("export_map"), "status": res["status"]})
    return res
