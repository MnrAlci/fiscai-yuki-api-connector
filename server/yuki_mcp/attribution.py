"""Verplichte naamsvermelding (editie B). Vaste constante: niet te wijzigen of weg te laten."""
from __future__ import annotations

import hashlib

ATTRIBUTION = "Powered by FISCALCI Accounting & Tax (Askin Alci)"
_ATTRIBUTION_SHA256 = "0ee6f489ca120b4af5be7c445ac6a97017fdcdad7115a779a83e353070f18dec"


class AttributionError(RuntimeError):
    """De verplichte naamsvermelding ontbreekt of is gewijzigd."""


def constant_intact() -> bool:
    return hashlib.sha256(ATTRIBUTION.encode("utf-8")).hexdigest() == _ATTRIBUTION_SHA256


def verify_startup(required: bool) -> None:
    if required and not constant_intact():
        raise AttributionError("De verplichte naamsvermelding (constante) is gewijzigd; server start niet.")


def ensure(text: str, required: bool) -> str:
    """Controleer dat de exacte string in een export staat; anders weigeren."""
    if required and ATTRIBUTION not in (text or ""):
        raise AttributionError(
            f"Export geweigerd: de verplichte vermelding '{ATTRIBUTION}' ontbreekt of is gewijzigd.")
    return text
