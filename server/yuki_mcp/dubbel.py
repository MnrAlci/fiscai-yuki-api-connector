"""Controle op dubbele boekingen vóór een boekingsvoorstel. Alleen gedocumenteerde leesmethode: AccountingInfo.GetTransactionDetails
(op de rekening van de relatie, in een beperkt venster rond de documentdatum; cache en maandgrenzen houden het aantal calls laag).
Uitkomsten: 'geen bestaande boeking gevonden', 'mogelijk al geboekt' of 'al geboekt'; bij een mislukte controle: 'controle niet uitgevoerd'.
Alles behalve 'geen' blokkeert (geen token) tenzij de gebruiker uitdrukkelijk deblokkeert met een reden (auditlog)."""
from __future__ import annotations

import calendar
import re
from datetime import date, timedelta
from decimal import Decimal
from typing import Any, Optional

GEEN = "geen bestaande boeking gevonden"
MOGELIJK = "mogelijk al geboekt"
AL = "al geboekt"
MISLUKT = "controle niet uitgevoerd"
VENSTER_DAGEN = 45
MIN_REDEN = 10
_RANG = {GEEN: 0, MOGELIJK: 1, AL: 2}


def _norm(s: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(s or "").casefold())


def blokkeert(uitkomst: str) -> bool:
    return uitkomst != GEEN


def venster(d: date) -> tuple[date, date]:
    """Venster van ±45 dagen, uitgelijnd op maandgrenzen (betere cachehits tussen items)."""
    van = (d - timedelta(days=VENSTER_DAGEN)).replace(day=1)
    e = d + timedelta(days=VENSTER_DAGEN)
    return van, e.replace(day=calendar.monthrange(e.year, e.month)[1])


def relatielijn(regels: list[dict]) -> Optional[dict]:
    return next((r for r in regels if r.get("relatie")), None)


def beoordeel(regel: dict, item: dict, aanpass: dict, txs: list) -> dict:
    """Pure beoordeling (geen netwerk). regel = de boekingsregel met de relatie (rekening, bedrag incl., datum, relatie)."""
    bedrag = Decimal(str(regel["bedrag"])).quantize(Decimal("0.01"))
    d = date.fromisoformat(regel["datum"])
    naam = _norm(regel.get("relatie"))
    ref = str(aanpass.get("referentie") or item.get("referentie") or "").strip()
    doc = str(item.get("id") or "").split(":", 1)[-1]
    beste = {"uitkomst": GEEN, "zekerheid": None, "redenen": [], "kandidaten": 0}

    def zet(uitkomst: str, zekerheid: str, reden: str) -> None:
        nonlocal beste
        if _RANG[uitkomst] > _RANG[beste["uitkomst"]] or (_RANG[uitkomst] == _RANG[beste["uitkomst"]] and uitkomst != GEEN
                                                         and ["laag", "midden", "hoog"].index(zekerheid) > ["laag", "midden", "hoog"].index(beste["zekerheid"] or "laag")):
            beste = {**beste, "uitkomst": uitkomst, "zekerheid": zekerheid, "redenen": [reden]}
        elif uitkomst == beste["uitkomst"] and reden not in beste["redenen"]:
            beste["redenen"].append(reden)
        beste["kandidaten"] += 1

    for t in txs:
        if t.amount is None:
            continue
        ta = Decimal(str(t.amount)).quantize(Decimal("0.01"))
        zelfde_contact = bool(naam) and _norm(t.contact) == naam
        zelfde_datum = bool(t.date) and t.date.date() == d
        drefs = _norm(t.document_reference)
        zoek = drefs + _norm(t.description)
        ref_match = len(_norm(ref)) >= 3 and _norm(ref) in zoek
        gekoppeld = bool(doc) and len(_norm(doc)) >= 4 and _norm(doc) == drefs
        zelfde = ta == bedrag
        tegengesteld = ta == -bedrag
        if gekoppeld:
            zet(AL, "hoog", "het document is al gekoppeld aan een transactie (documentreferentie)")
        elif zelfde and (ref_match or (zelfde_contact and zelfde_datum)):
            zet(AL, "hoog", "zelfde bedrag en " + ("zelfde referentie/factuurnummer" if ref_match else "zelfde relatie en documentdatum"))
        elif zelfde and (zelfde_contact or zelfde_datum):
            zet(MOGELIJK, "midden", "zelfde bedrag en " + ("zelfde relatie" if zelfde_contact else "zelfde datum") + ", verschillende referentie of datum")
        elif ref_match and not tegengesteld:
            zet(MOGELIJK, "laag", "zelfde referentie/factuurnummer maar ander bedrag of andere relatie")
        elif tegengesteld and (ref_match or zelfde_contact):
            zet(MOGELIJK, "midden" if (ref_match or zelfde_datum) else "laag",
                "zelfde bedrag met tegengesteld teken" + (" en zelfde referentie" if ref_match else " voor dezelfde relatie") + " (creditnota, terugboeking of betaling?)")
    beste["gecontroleerde_transacties"] = len(txs)
    return beste


def controleer(h: Any, regels: list[dict], item: dict, aanpass: dict) -> dict:
    """Voert de controle uit; elke fout geeft 'controle niet uitgevoerd' (en dus een blokkade)."""
    try:
        rl = relatielijn(regels)
        if rl is None:
            return {"uitkomst": MISLUKT, "zekerheid": None, "redenen": ["geen relatieregel in het voorstel om op te controleren"], "kandidaten": 0}
        van, tot = venster(date.fromisoformat(rl["datum"]))
        txs = h.gl_transactions(rl["rekening"], van, tot)
        res = beoordeel(rl, item, aanpass, txs)
        res["venster"] = f"{van.isoformat()} tot {tot.isoformat()}"
        res["rekening"] = rl["rekening"]
        res["methode"] = "AccountingInfo.GetTransactionDetails"
        return res
    except Exception as e:                    # fout of limiet: veilig blokkeren
        return {"uitkomst": MISLUKT, "zekerheid": None, "redenen": [f"controle mislukt ({type(e).__name__}); item geblokkeerd"], "kandidaten": 0}
