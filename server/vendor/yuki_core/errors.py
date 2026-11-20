"""Foutklassen."""

from __future__ import annotations


class YukiError(Exception):
    """Basisfout voor deze client."""


class YukiConfigError(YukiError):
    """Ontbrekende of ongeldige configuratie (env vars, cache key)."""


class YukiSoapFault(YukiError):
    """SOAP Fault teruggegeven door Yuki."""

    def __init__(self, method: str, faultcode: str, faultstring: str):
        self.method = method
        self.faultcode = faultcode
        self.faultstring = faultstring
        super().__init__(f"{method}: {faultcode}: {faultstring}")

    @property
    def is_invalid_session(self) -> bool:
        """True als de fout wijst op een ongeldige/verlopen sessie."""
        if self.method.startswith("Authenticate"):
            return False  # een mislukte login is geen 'sessie verlopen'
        text = f"{self.faultcode} {self.faultstring}".lower()
        markers = (
            "invalid session", "session is invalid", "session invalid", "sessionid",
            "session id", "session expired", "session has expired", "expired session",
            "not authenticated", "unauthenticated", "unauthorized", "ongeldige sessie",
            "sessie is verlopen", "sessie verlopen", "not logged in",
        )
        return any(m in text for m in markers)


class YukiDossierNotFound(YukiError):
    """Geen administratie gevonden voor de opgegeven naam of ID."""


class YukiAmbiguousDossier(YukiError):
    """Naam komt overeen met meerdere administraties."""

    def __init__(self, query: str, candidates: list):
        self.candidates = candidates
        names = ", ".join(c.name for c in candidates[:10])
        super().__init__(f"'{query}' is niet eenduidig; kandidaten: {names}")


class YukiDailyLimitReached(YukiError):
    """Daglimiet van Yuki-calls bereikt; de call is NIET verstuurd."""

    def __init__(self, status: dict):
        self.status = status
        super().__init__(
            f"daglimiet bereikt voor Yuki-domein {status.get('domain')}: "
            f"{status.get('calls')}/{status.get('limit')} calls op {status.get('day')} "
            f"(Europe/Brussels). Niet verstuurd; {len(status.get('open_requests', []))} verzoek(en) "
            f"staan open tot {status.get('resets_at')}. Meer calls alleen na uitdrukkelijk akkoord van de gebruiker.")
