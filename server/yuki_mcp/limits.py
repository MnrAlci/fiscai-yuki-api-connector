"""Instelbare daglimiet: standaard 900, vrij tot 1000, daarboven alleen met akkoord.

Yuki: 1000 calls per domein per dag zijn gratis.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field

DEFAULT_LIMIT = 900
FREE_LIMIT = 1000
GRATIS_TEKST = "Yuki: 1000 calls per domein per dag zijn gratis."


@dataclass
class LimitConfig:
    limit: int
    warn_at: int
    requested: int
    approved_over_free: bool = False
    warnings: list[str] = field(default_factory=list)


def resolve_limit(env: dict | None = None) -> LimitConfig:
    """Bepaal de effectieve limiet uit YUKI_DAILY_LIMIT / YUKI_DAILY_LIMIT_APPROVAL.

    - leeg of ongeldig → 900 (ongeldig geeft een waarschuwing)
    - 1..1000 → zoals ingesteld, zonder akkoord
    - >1000 zonder akkoord → begrensd op 1000 + waarschuwing
    - >1000 met akkoord → zoals ingesteld + waarschuwing dat kosten kunnen volgen
    """
    env = os.environ if env is None else env
    warnings: list[str] = []
    raw = str(env.get("YUKI_DAILY_LIMIT", "")).strip()
    requested = DEFAULT_LIMIT
    if raw:
        try:
            requested = int(raw)
        except ValueError:
            warnings.append(f"YUKI_DAILY_LIMIT is geen geheel getal; standaard {DEFAULT_LIMIT} gebruikt.")
            requested = DEFAULT_LIMIT
    if requested < 1:
        warnings.append(f"YUKI_DAILY_LIMIT moet minstens 1 zijn; standaard {DEFAULT_LIMIT} gebruikt.")
        requested = DEFAULT_LIMIT
    approval = str(env.get("YUKI_DAILY_LIMIT_APPROVAL", "")).strip()
    limit = requested
    approved = False
    if requested > FREE_LIMIT:
        if approval:
            approved = True
            warnings.append(
                f"WAARSCHUWING: daglimiet {requested} ligt boven {FREE_LIMIT}; "
                "buiten de gratis staffel kunnen kosten volgen (akkoord ingesteld). " + GRATIS_TEKST)
        else:
            limit = FREE_LIMIT
            warnings.append(
                f"Gevraagde daglimiet {requested} > {FREE_LIMIT} zonder bevestiging "
                f"(YUKI_DAILY_LIMIT_APPROVAL): begrensd op {FREE_LIMIT}. " + GRATIS_TEKST)
    warn_raw = str(env.get("YUKI_DAILY_WARN", "")).strip()
    warn = int(limit * 0.8)
    if warn_raw:
        try:
            w = int(warn_raw)
            if 0 < w <= limit:
                warn = w
            else:
                warnings.append("YUKI_DAILY_WARN buiten bereik; 80 % van de limiet gebruikt.")
        except ValueError:
            warnings.append("YUKI_DAILY_WARN is geen geheel getal; 80 % van de limiet gebruikt.")
    return LimitConfig(limit=limit, warn_at=max(1, warn), requested=requested,
                       approved_over_free=approved, warnings=warnings)
