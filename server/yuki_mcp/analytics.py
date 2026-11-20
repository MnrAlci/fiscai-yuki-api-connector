"""Deterministische analyses op Yuki-leesdata. Pure functies, geen netwerk, geen verzonnen cijfers.

Tekenconventie (zie handleiding.py): grootboeksaldo = debet - credit (opbrengsten dus negatief);
openstaande posten: positief = nog te ontvangen (debiteuren) of nog te betalen (crediteuren),
negatief = meestal een betaling zonder (gekoppelde) factuur; minder vaak creditnota, voorschot of te veel betaald (na te gaan). Live bevestigd in één dossier (zie handleiding); verifieer in het
eigen dossier.
"""
from __future__ import annotations

import re

import statistics
from collections import defaultdict
from datetime import date, datetime, timedelta
from decimal import Decimal
from typing import Any, Iterable, Optional

ZERO = Decimal(0)
CENT = Decimal("0.01")
BUCKETS = ("niet_vervallen", "0-30", "31-60", "61-90", ">90", "zonder_datum")


def D(x: Any) -> Decimal:
    if x is None or x == "":
        return ZERO
    return x if isinstance(x, Decimal) else Decimal(str(x))


def money(x: Decimal) -> float:
    return float(D(x).quantize(CENT))


def _d(x: Any) -> Optional[date]:
    if x is None:
        return None
    if isinstance(x, datetime):
        return x.date()
    if isinstance(x, date):
        return x
    return datetime.fromisoformat(str(x)).date()


def _get(it: Any, name: str) -> Any:
    return it.get(name) if isinstance(it, dict) else getattr(it, name, None)


def bucket_for(dagen_over_tijd: Optional[int]) -> str:
    if dagen_over_tijd is None:
        return "zonder_datum"
    if dagen_over_tijd <= 0:
        return "niet_vervallen"
    if dagen_over_tijd <= 30:
        return "0-30"
    if dagen_over_tijd <= 60:
        return "31-60"
    if dagen_over_tijd <= 90:
        return "61-90"
    return ">90"


NEG_LABEL = "negatief open bedrag: waarschijnlijk betaling zonder factuur (na te gaan)"
NEG_TOELICHTING = ("Meestal een betaling waar (nog) geen factuur tegenover staat of aan gekoppeld is: bij leveranciers de factuur opvragen of "
                   "laten bezorgen, bij klanten de factuur nakijken of laten bezorgen. Minder vaak een creditnota, een voorschot of een te veel betaald bedrag.")
_TYPE_RE = (
    ("creditnota", re.compile(r"credit\s*-?\s*(nota|note|memo)|\bcn\b|\bnc\b", re.I)),
    ("betaling", re.compile(r"betaling|betaald|payment|ontvangst|overschrijving|\bbank\b|domicili|coda", re.I)),
    ("voorschot", re.compile(r"voorschot|aanbetaling|advance|deposit|prepay", re.I)),
)


def negatief_type(item: Any) -> str:
    """Type van een negatieve post, enkel afgeleid uit wat Yuki zelf meegeeft (omschrijving/referentie).
    Geen treffer = 'onbekend type' (niet gokken)."""
    tekst = f"{_get(item, 'description') or ''} {_get(item, 'reference') or ''}"
    hits = [naam for naam, rx in _TYPE_RE if rx.search(tekst)]
    return hits[0] if len(hits) == 1 else "onbekend type"


def ouderdomsanalyse(items: Iterable[Any], peildatum: date | datetime | str, basis: str = "vervaldatum") -> dict:
    """Ouderdom van openstaande posten. basis: 'vervaldatum' (dagen na vervaldag) of 'factuurdatum'.

    Buckets 0-30/31-60/61-90/>90 = dagen na de basisdatum; 'niet_vervallen' = nog niet over de basisdatum.
    Positieve posten tellen in de buckets; negatieve posten staan apart onder een neutraal label.
    """
    if basis not in ("vervaldatum", "factuurdatum"):
        raise ValueError("basis moet 'vervaldatum' of 'factuurdatum' zijn")
    peil = _d(peildatum)
    buckets = {b: ZERO for b in BUCKETS}
    counts = {b: 0 for b in BUCKETS}
    negatieven = ZERO
    n_neg = 0
    types: dict[str, int] = {}
    for it in items:
        open_amt = D(_get(it, "open_amount"))
        ref = _d(_get(it, "due_date")) if basis == "vervaldatum" else _d(_get(it, "date"))
        if open_amt < 0:
            negatieven += open_amt
            n_neg += 1
            t = negatief_type(it)
            types[t] = types.get(t, 0) + 1
            continue
        dagen = (peil - ref).days if ref else None
        b = bucket_for(dagen)
        buckets[b] += open_amt
        counts[b] += 1
    totaal_pos = sum(buckets.values(), ZERO)
    return {
        "peildatum": peil.isoformat(), "basis": basis,
        "buckets": {b: {"bedrag": money(buckets[b]), "aantal": counts[b]} for b in BUCKETS},
        "totaal_positief": money(totaal_pos),
        "negatieve_posten": {"label": NEG_LABEL, "toelichting": NEG_TOELICHTING, "bedrag": money(negatieven), "aantal": n_neg, "types": types},
        "netto": money(totaal_pos + negatieven),
        "vervallen_totaal": money(sum((buckets[b] for b in ("0-30", "31-60", "61-90", ">90")), ZERO)),
    }


def dagen_ratio(open_saldo: Decimal | float, basis_bedrag: Decimal | float, dagen: int,
                btw_percentage: Optional[float] = None) -> dict:
    """DSO/DPO = openstaand / (omzet of inkopen) x aantal dagen. Optionele btw-correctie op de noemer."""
    noemer = D(basis_bedrag)
    if btw_percentage:
        noemer = noemer * (1 + D(btw_percentage) / 100)
    if noemer <= 0 or dagen <= 0:
        return {"waarde_dagen": None, "reden": "noemer of aantal dagen is niet positief",
                "openstaand": money(D(open_saldo)), "basis": money(noemer), "dagen": dagen}
    waarde = D(open_saldo) / noemer * dagen
    return {"waarde_dagen": float(waarde.quantize(Decimal("0.1"))), "openstaand": money(D(open_saldo)),
            "basis": money(noemer), "dagen": dagen,
            "formule": "openstaand / basis x dagen",
            "btw_correctie_pct": btw_percentage or 0,
            "opmerking": "Indicatie: openstaande posten zijn doorgaans incl. btw, omzet/inkopen excl. btw; "
                         "geef btw_percentage mee voor een correctie."}


def top_relaties(items: Iterable[Any], n: int = 10) -> list[dict]:
    agg: dict[str, dict] = {}
    for it in items:
        name = (_get(it, "contact") or "[onbekend]")
        rec = agg.setdefault(name, {"relatie": name, "openstaand": ZERO, "posten": 0, "oudste_vervaldatum": None})
        rec["openstaand"] += D(_get(it, "open_amount"))
        rec["posten"] += 1
        dd = _d(_get(it, "due_date"))
        if dd and (rec["oudste_vervaldatum"] is None or dd < rec["oudste_vervaldatum"]):
            rec["oudste_vervaldatum"] = dd
    out = sorted(agg.values(), key=lambda r: (-r["openstaand"], r["relatie"]))[: max(1, n)]
    total = sum((r["openstaand"] for r in agg.values()), ZERO)
    return [{"relatie": r["relatie"], "openstaand": money(r["openstaand"]), "posten": r["posten"],
             "oudste_vervaldatum": r["oudste_vervaldatum"].isoformat() if r["oudste_vervaldatum"] else None,
             "aandeel_pct": float((r["openstaand"] / total * 100).quantize(Decimal("0.1"))) if total else None}
            for r in out]


# ------------------------------------------------------------- resultaat per periode
def _line(l: Any, k: str) -> Any:
    return l.get(k) if isinstance(l, dict) else getattr(l, k, None)


def _saldo(l: Any) -> Decimal:
    b = _line(l, "balance")
    if b is not None:
        return D(b)
    return D(_line(l, "debit")) - D(_line(l, "credit"))


def pl_periode(lines_end: Iterable[Any], lines_start_prev: Optional[Iterable[Any]] = None) -> dict:
    """Resultaat over een periode: saldo(einddatum) - saldo(dag voor start), per rekening (klasse 6 en 7).

    Veronderstelling: resultaatrekeningen zijn cumulatief binnen het boekjaar (reset bij nieuw boekjaar).
    Een periode die over een boekjaarwissel loopt wordt daardoor niet correct berekend.
    """
    prev = {str(_line(l, "code")): _saldo(l) for l in (lines_start_prev or [])}
    rows = {}
    for l in lines_end:
        code = str(_line(l, "code") or "").strip()
        digits = "".join(ch for ch in code if ch.isdigit())
        if not digits or digits[0] not in "67":
            continue
        rows[code] = (_saldo(l) - prev.get(code, ZERO), _line(l, "name"))
    for code, s in prev.items():
        digits = "".join(ch for ch in code if ch.isdigit())
        if code not in rows and digits and digits[0] in "67":
            rows[code] = (-s, None)
    omzet = kosten = opbr_totaal = ZERO
    kost_klassen: dict[str, Decimal] = defaultdict(lambda: ZERO)
    handelsgoed = ZERO
    for code, (v, _n) in rows.items():
        dg = "".join(ch for ch in code if ch.isdigit())
        two = dg[:2]
        if dg[0] == "7" and two != "79":
            opbr_totaal += -v
            if two == "70":
                omzet += -v
        elif dg[0] == "6" and two != "69":
            kosten += v
            kost_klassen[two] += v
            if two == "60":
                handelsgoed += v
    resultaat = opbr_totaal - kosten
    return {"omzet": omzet, "opbrengsten": opbr_totaal, "kosten": kosten, "resultaat": resultaat,
            "kosten_per_klasse": dict(kost_klassen), "inkopen_60": handelsgoed}


def _pct(a: Decimal, b: Decimal) -> Optional[float]:
    return float((a / b * 100).quantize(Decimal("0.1"))) if b else None


def marge_kostenstructuur(pl: dict) -> dict:
    omzet, kosten = pl["omzet"], pl["kosten"]
    brutomarge = omzet - pl["inkopen_60"]
    return {
        "omzet": money(omzet), "inkopen_60": money(pl["inkopen_60"]),
        "brutomarge": money(brutomarge), "brutomarge_pct": _pct(brutomarge, omzet),
        "kosten_totaal": money(kosten), "resultaat": money(pl["resultaat"]),
        "nettomarge_pct": _pct(pl["resultaat"], omzet),
        "kostenstructuur": [
            {"klasse": k, "bedrag": money(v), "pct_van_kosten": _pct(v, kosten), "pct_van_omzet": _pct(v, omzet)}
            for k, v in sorted(pl["kosten_per_klasse"].items())],
        "opmerking": "Klasse 60 = handelsgoederen, grond- en hulpstoffen; 61 diensten en diverse goederen; "
                     "62 bezoldigingen; 63 afschrijvingen; 64 overige bedrijfskosten; 65 financiële kosten; "
                     "66 uitzonderlijke kosten; 67 belastingen (MAR). Bij een afwijkend rekeningschema: verifieer.",
    }


def periode_bereik(jaar: int, periode: str) -> tuple[date, date]:
    """periode: 'jaar', 'kwartaal:1..4' of 'maand:1..12' → (start, einde)."""
    if periode == "jaar":
        return date(jaar, 1, 1), date(jaar, 12, 31)
    kind, _, n = periode.partition(":")
    if kind == "kwartaal" and n.isdigit() and 1 <= int(n) <= 4:
        q = int(n)
        s = date(jaar, 3 * (q - 1) + 1, 1)
        e = (date(jaar + (q == 4), (3 * q) % 12 + 1, 1) - timedelta(days=1))
        return s, e
    if kind == "maand" and n.isdigit() and 1 <= int(n) <= 12:
        m = int(n)
        s = date(jaar, m, 1)
        e = date(jaar + (m == 12), m % 12 + 1, 1) - timedelta(days=1)
        return s, e
    raise ValueError("periode moet 'jaar', 'kwartaal:1-4' of 'maand:1-12' zijn")


def vorige_periode(jaar: int, periode: str) -> tuple[int, str]:
    if periode == "jaar":
        return jaar - 1, "jaar"
    kind, _, n = periode.partition(":")
    n = int(n)
    if n > 1:
        return jaar, f"{kind}:{n - 1}"
    return jaar - 1, f"{kind}:{4 if kind == 'kwartaal' else 12}"


def vergelijk(a: dict, b: dict, labels: tuple[str, str] = ("huidig", "vergelijking")) -> dict:
    out = {}
    for k in ("omzet", "kosten", "resultaat"):
        va, vb = a[k], b[k]
        out[k] = {labels[0]: money(va), labels[1]: money(vb), "verschil": money(va - vb),
                  "verschil_pct": _pct(va - vb, abs(vb)) if vb else None}
    return out


def liquiditeit_uit_ratios(ratios: dict) -> dict:
    keep = ("liquiditeit", "cash_ratio", "working_capital", "solvabiliteit", "debt_ratio")
    return {k: {"waarde": ratios[k]["waarde"], "formule": ratios[k]["formule"], "reden": ratios[k].get("reden")}
            for k in keep if k in ratios}


def btw_saldo_indicatie(lines: Iterable[Any]) -> dict:
    """Indicatie uit rekeningen 411 (btw te vorderen) en 451 (btw te betalen), MAR. Geen aangifte."""
    vord = betal = ZERO
    for l in lines:
        dg = "".join(ch for ch in str(_line(l, "code") or "") if ch.isdigit())
        if dg.startswith("411"):
            vord += _saldo(l)
        elif dg.startswith("451"):
            betal += -_saldo(l)
    return {"btw_te_vorderen_411": money(vord), "btw_te_betalen_451": money(betal),
            "netto_te_betalen": money(betal - vord),
            "opmerking": "Indicatie op basis van grootboekrekeningen 411 en 451 volgens het MAR; "
                         "geen btw-aangifte. Verifieer de rekeningcodes in het eigen rekeningschema."}


# ----------------------------------------------------------------- uitschieters
def uitschieters(transacties: Iterable[Any], drempel: float = 3.5, min_aantal: int = 8) -> dict:
    """Uitschieters op |bedrag| via gemodificeerde z-score (mediaan/MAD, drempel 3.5 volgens Iglewicz-Hoaglin),
    plus dubbele boekingen (zelfde datum, bedrag en omschrijving). Deterministisch, geen oordeel."""
    txs = list(transacties)
    amounts = [abs(float(D(_get(t, "amount")))) for t in txs]
    res = {"aantal_transacties": len(txs), "methode": "gemodificeerde z-score (mediaan/MAD)", "drempel": drempel,
           "uitschieters": [], "mogelijk_dubbel": []}
    if len(txs) >= min_aantal:
        med = statistics.median(amounts)
        mad = statistics.median([abs(a - med) for a in amounts])
        res["mediaan"] = round(med, 2)
        res["mad"] = round(mad, 2)
        if mad > 0:
            for t, a in zip(txs, amounts):
                z = 0.6745 * (a - med) / mad
                if abs(z) > drempel:
                    res["uitschieters"].append({
                        "id": _get(t, "id"), "datum": (_d(_get(t, "date")).isoformat() if _get(t, "date") else None),
                        "omschrijving": _get(t, "description"), "bedrag": money(D(_get(t, "amount"))),
                        "z_score": round(z, 2)})
        else:
            res["opmerking"] = "MAD is 0 (nagenoeg identieke bedragen): geen z-score berekend."
    else:
        res["opmerking"] = f"Minder dan {min_aantal} transacties: geen statistische uitschieters berekend."
    seen: dict[tuple, list] = defaultdict(list)
    for t in txs:
        seen[(str(_d(_get(t, "date"))), str(D(_get(t, "amount"))), (_get(t, "description") or "").strip().lower())].append(t)
    for key, group in seen.items():
        if len(group) > 1:
            res["mogelijk_dubbel"].append({"datum": key[0], "bedrag": float(D(key[1])), "omschrijving": key[2],
                                           "aantal": len(group), "ids": [_get(g, "id") for g in group]})
    return res
