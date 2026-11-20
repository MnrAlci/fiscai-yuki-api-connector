"""``yuki_status``: dagteller per domein en grootte van de antwoordcache.

Toont nooit geheimen (geen access key, geen sessie) en geen cijfers uit
dossiers: alleen aantallen calls, resterend en cachegrootte. Doet zelf geen
enkele Yuki-call en heeft geen YUKI_ACCESS_KEY nodig.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Optional

from .errors import YukiError
from .quota import DailyQuota
from .response_cache import ResponseCache


def collect_status(data_dir: Optional[Path | str] = None,
                   cache_dir: Optional[Path | str] = None, clock=None) -> dict:
    kw = {"clock": clock} if clock else {}
    quota = DailyQuota(data_dir, **kw)
    rc = ResponseCache(cache_dir, **kw)
    cache = rc.stats()
    domains = []
    seen = set()
    for st in quota.all_today():
        seen.add(st.domain)
        d = st.to_dict()
        domains.append({"domain": st.domain, "calls_today": st.calls,
                        "authenticates": st.authenticates, "remaining": st.remaining,
                        "limit": st.limit, "warn_at": st.warn_at, "status": d["status"],
                        "blocked": st.blocked, "open_requests": len(st.open_requests),
                        "cache": cache.get(st.domain, {"entries": 0, "valid": 0, "bytes": 0})})
    for dom, c in sorted(cache.items()):
        if dom not in seen:
            domains.append({"domain": dom, "calls_today": 0, "authenticates": 0,
                            "remaining": quota.limit, "limit": quota.limit, "warn_at": quota.warn_at,
                            "status": "ok", "blocked": 0, "open_requests": 0, "cache": c})
    return {"day": quota.today(), "timezone": "Europe/Brussels", "limit": quota.limit,
            "warn_at": quota.warn_at, "counter_file": str(quota.path),
            "cache_dir": str(rc.dir), "domains": domains}


def _human(n: int) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if n < 1024:
            return f"{n:.0f} {unit}"
        n /= 1024  # type: ignore[assignment]
    return f"{n:.1f} TB"


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="yuki_status", description="Yuki-dagteller en cache")
    p.add_argument("--json", action="store_true", help="JSON-uitvoer")
    args = p.parse_args(argv)
    try:
        s = collect_status()
    except YukiError as exc:
        print(f"fout: {exc}", file=sys.stderr)
        return 1
    if args.json:
        print(json.dumps(s, indent=2, ensure_ascii=False))
        return 0
    print(f"Yuki-status {s['day']} (Europe/Brussels) – limiet {s['limit']}/dag/domein, "
          f"waarschuwing vanaf {s['warn_at']}")
    if not s["domains"]:
        print("Nog geen calls vandaag en geen cache.")
    for d in s["domains"]:
        c = d["cache"]
        print(f"- {d['domain']}: {d['calls_today']} calls vandaag (waarvan {d['authenticates']} "
              f"Authenticate), {d['remaining']} resterend, status {d['status']}"
              + (f", {d['open_requests']} open verzoek(en)" if d["open_requests"] else "")
              + f"; cache {c['valid']}/{c['entries']} geldig, {_human(c['bytes'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
