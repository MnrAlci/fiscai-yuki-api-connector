"""Leestools voor het Yuki-accountantsportaal.

Eén gedeelde ``YukiClient`` (en dus één gecachete sessie) per proces, en
hoogstens één geopend dossier tegelijk. ``yuki_close_dossier()`` geeft het
dossier vrij maar laat de 24u-sessie staan.

``yuki_analyze_dossier`` berekent jaartotalen en ratio's (``yearly_totals.json``)
bovenop de proef- en saldibalans en de netto-omzet. Nog niet geïmplementeerd:
achterstallige debiteuren/crediteuren, omzetevolutie, btw-saldo en export naar
het V4.5-sjabloon 'voorlopige cijfers'.
"""

from __future__ import annotations

import contextlib
import threading
from dataclasses import asdict
from datetime import date, datetime
from typing import Any, Literal, Optional

from . import analysis
from .client import DossierHandle, YukiClient
from .errors import YukiError, YukiSoapFault

_lock = threading.Lock()
_client: Optional[YukiClient] = None
_dossier: Optional[DossierHandle] = None

DateLike = date | datetime | str


def configure(client: Optional[YukiClient]) -> None:
    """Injecteer een client (tests/embedding). ``None`` → bij volgend gebruik uit env."""
    global _client, _dossier
    with _lock:
        if _dossier is not None:
            _dossier.close()
        _dossier = None
        _client = client


def _get_client() -> YukiClient:
    global _client
    with _lock:
        if _client is None:
            _client = YukiClient.from_env()
        return _client


def _require_dossier() -> DossierHandle:
    if _dossier is None or _dossier.closed:
        raise YukiError("Geen dossier geopend; roep eerst yuki_open_dossier(naam_of_id) aan")
    return _dossier


@contextlib.contextmanager
def _refresh(handle: DossierHandle, force_refresh: bool):
    prev = handle.force_refresh
    handle.force_refresh = prev or force_refresh
    try:
        yield handle
    finally:
        handle.force_refresh = prev


def _plain(obj: Any) -> Any:
    return asdict(obj) if hasattr(obj, "__dataclass_fields__") else obj


# ---------------------------------------------------------------- tools
def yuki_get_session() -> dict:
    """Geldige sessie (Authenticate alleen bij miss/verval). Geeft géén session ID terug."""
    c = _get_client()
    s = c.sessions.get_session()
    return {"ok": True, "scope": s.scope, "key_fingerprint": s.key_fp[:10],
            "obtained_at": s.obtained_at.isoformat(), "expires_at": s.expires_at.isoformat(),
            "calls_today": c.sessions.calls_today}


def yuki_list_dossiers(with_internal_code: bool = False, force_refresh: bool = False) -> list[dict]:
    """AccountingInfo.Administrations (of ...WithInternalCustomerCode)."""
    return [_plain(a) for a in _get_client().list_administrations(
        with_internal_code=with_internal_code, refresh=force_refresh)]


def yuki_status() -> dict:
    """Dagteller per domein + grootte van de antwoordcache. Geen geheimen of cijfers."""
    from .status import collect_status
    return collect_status()


def yuki_open_dossier(naam_of_id: str) -> dict:
    """Open een scoped verbinding voor één administratie (naam of Administration ID)."""
    global _dossier
    c = _get_client()
    handle = c.open_dossier(naam_of_id)
    with _lock:
        if _dossier is not None:
            _dossier.close()
        _dossier = handle
    return _plain(handle.administration)


def yuki_get_trial_balance(datum: DateLike, fiscaal: bool = False,
                           force_refresh: bool = False) -> list[dict]:
    """Proef- en saldibalans op ``datum`` (GLAccountBalance / GLAccountBalanceFiscal)."""
    with _refresh(_require_dossier(), force_refresh) as h:
        return [_plain(l) for l in h.trial_balance(datum, fiscaal=fiscaal)]


def yuki_get_net_revenue(van: DateLike, tot: DateLike, fiscaal: bool = False,
                         force_refresh: bool = False) -> dict:
    """Netto-omzet tussen ``van`` en ``tot`` (NetRevenue / NetRevenueFiscal)."""
    with _refresh(_require_dossier(), force_refresh) as h:
        return _plain(h.net_revenue(van, tot, fiscaal=fiscaal))


def yuki_get_open_items(soort: Literal["debiteuren", "crediteuren"],
                        peildatum: Optional[DateLike] = None, force_refresh: bool = False) -> list[dict]:
    """Openstaande posten (Outstanding{Debtor|Creditor}Items[ByDateOutstanding])."""
    with _refresh(_require_dossier(), force_refresh) as h:
        items = h.open_items(soort, peildatum=peildatum)
    return [{k: v for k, v in _plain(i).items() if k != "raw"} for i in items]


def yuki_get_gl_transactions(rekening: str, van: DateLike, tot: DateLike,
                             force_refresh: bool = False) -> list[dict]:
    """Boekingen op één grootboekrekening (AccountingInfo.GetTransactionDetails)."""
    with _refresh(_require_dossier(), force_refresh) as h:
        return [_plain(t) for t in h.gl_transactions(rekening, van, tot)]


def yuki_close_dossier() -> dict:
    """Dossierhandle + opgehaalde data vrijgeven; de gecachete sessie blijft."""
    global _dossier
    with _lock:
        closed = _dossier is not None
        if _dossier is not None:
            _dossier.close()
        _dossier = None
    return {"closed": closed, "session_kept": True}


def _boekjaar_bounds(boekjaar: Optional[int | str], van: Optional[DateLike],
                     tot: Optional[DateLike]) -> tuple[DateLike, DateLike, Optional[str]]:
    """Kalenderjaar uit ``boekjaar``; ``van``/``tot`` overschrijven (gebroken boekjaar)."""
    label = str(boekjaar) if boekjaar is not None else None
    if boekjaar is not None:
        try:
            year = int(boekjaar)
        except (TypeError, ValueError) as exc:
            raise ValueError("boekjaar moet een jaartal zijn, bv. 2025") from exc
        van = van if van is not None else date(year, 1, 1)
        tot = tot if tot is not None else date(year, 12, 31)
    if van is None or tot is None:
        raise ValueError("geef een boekjaar, of zowel van als tot")
    return van, tot, label


def yuki_analyze_dossier(boekjaar: Optional[int | str] = None, *, van: Optional[DateLike] = None,
                         tot: Optional[DateLike] = None, financial_mode: int = 0,
                         naam_of_id: Optional[str] = None,
                         klasse4: Literal["saldo", "rubriek"] = "saldo",
                         output_path: Optional[str] = None, force_refresh: bool = False) -> dict:
    """Jaartotalen + ratio's voor het geopende dossier (``yearly_totals.json``-vorm).

    Leest alleen: proef- en saldibalans op ``tot`` (GLAccountBalance of
    GLAccountBalanceFiscal) en netto-omzet ``van``–``tot`` (NetRevenue of
    NetRevenueFiscal). ``financial_mode``: 0 = commercieel (standaard),
    1 = fiscaal – een aanname, niet live bevestigd. ``naam_of_id`` opent eerst
    dat dossier. Schrijft alleen naar schijf als ``output_path`` gegeven is.
    """
    if financial_mode not in analysis.FINANCIAL_MODES:
        raise ValueError("financial_mode moet 0 (commercieel) of 1 (fiscaal) zijn")
    start, end, label = _boekjaar_bounds(boekjaar, van, tot)
    if naam_of_id:
        yuki_open_dossier(naam_of_id)
    handle = _require_dossier()
    with _refresh(handle, force_refresh):
        return _analyze(handle, financial_mode, start, end, label, klasse4, output_path)


def _analyze(handle: DossierHandle, financial_mode: int, start: DateLike, end: DateLike,
             label: Optional[str], klasse4: str, output_path: Optional[str]) -> dict:
    fiscaal = financial_mode == 1
    tb_method = "GLAccountBalanceFiscal" if fiscaal else "GLAccountBalance"
    nr_method = "NetRevenueFiscal" if fiscaal else "NetRevenue"
    lines = handle.trial_balance(end, fiscaal=fiscaal)
    extra: list[str] = []
    try:
        net_revenue = handle.net_revenue(start, end, fiscaal=fiscaal).amount
    except YukiSoapFault as exc:
        if exc.is_invalid_session:
            raise
        net_revenue = None
        extra.append(f"{nr_method} gaf een fout ({exc.faultcode}); omzet uit klasse 70.")
    admin = handle.administration
    result = analysis.analyze_trial_balance(
        lines, net_revenue=net_revenue, financial_mode=financial_mode, klasse4=klasse4,
        administration_id=admin.id, administration_name=admin.name,
        boekjaar=label, van=start, tot=end,
        bronnen={"trial_balance": f"Accounting.{tb_method}", "net_revenue": f"Accounting.{nr_method}"},
        extra_aannames=extra)
    if output_path:
        result.write(output_path)
    return result.to_dict()
