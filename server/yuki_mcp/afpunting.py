"""Afpuntingsvoorstellen voor openstaande posten (debiteuren en crediteuren). Alleen voorstellen, nooit afpunten.

Teken (na normalisatie, zie tools._items): open bedrag > 0 = factuur nog open; < 0 = negatief open bedrag, meestal een
betaling waar (nog) geen factuur aan gekoppeld is. Pure functies, geen netwerk.
"""
from __future__ import annotations

import difflib
import re
from datetime import date
from decimal import Decimal
from typing import Any, Iterable, Optional

from .analytics import D, ZERO, _d, _get, money

MAX_POSTEN_HARD = 8
MAX_COMBINATIES_HARD = 200_000
DREMPEL_MAIL = 0.5          # voorstellen met zekerheid >= dit tellen als 'mogelijk al betaald' in de herinneringsmail
_FORMS = re.compile(r"\b(bv|bvba|srl|sprl|nv|sa|vzw|asbl|cv|comm\.?v|gcv|vof|snc|ltd|gmbh|bv\s*ba)\b\.?", re.I)
_TOKEN = re.compile(r"[A-Za-z0-9][A-Za-z0-9\-/.]{2,}")


def item_key(it: Any) -> str:
    return f"{_get(it, 'contact') or ''}|{_get(it, 'reference') or ''}|{_get(it, 'date') or ''}|{D(_get(it, 'open_amount'))}"


def norm_name(n: Any) -> str:
    s = _FORMS.sub(" ", str(n or "").casefold())
    return re.sub(r"[^a-z0-9]+", " ", s).strip()


def ref_tokens(it: Any) -> set[str]:
    txt = f"{_get(it, 'reference') or ''} {_get(it, 'description') or ''}"
    out = set()
    for t in _TOKEN.findall(txt):
        t = t.strip("-/.").casefold()
        if len(t) >= 4 and any(ch.isdigit() for ch in t):
            out.add(t)
    return out


def _label(score: float) -> str:
    return "hoog" if score >= 0.8 else "middel" if score >= 0.5 else "laag"


class _Doc:
    __slots__ = ("idx", "it", "bedrag", "relatie", "code", "rol", "tokens", "naam")

    def __init__(self, idx: int, it: Any) -> None:
        self.idx, self.it = idx, it
        self.bedrag = D(_get(it, "open_amount"))
        self.relatie = _get(it, "contact") or "[onbekend]"
        self.code = _get(it, "contact_code")
        self.rol = "betaling" if self.bedrag < 0 else "factuur"
        self.tokens = ref_tokens(it)
        self.naam = norm_name(self.relatie)

    def rel_key(self) -> str:
        return f"c:{self.code}" if self.code else f"n:{self.naam}"

    def to_dict(self) -> dict:
        return {"id": f"P{self.idx}", "rol": self.rol, "relatie": self.relatie, "referentie": _get(self.it, "reference"),
                "omschrijving": _get(self.it, "description"),
                "datum": (_d(_get(self.it, "date")).isoformat() if _d(_get(self.it, "date")) else None),
                "vervaldatum": (_d(_get(self.it, "due_date")).isoformat() if _d(_get(self.it, "due_date")) else None),
                "bedrag": money(abs(self.bedrag)), "open_bedrag": money(self.bedrag)}


def _subsets(cands: list[_Doc], target: Decimal, tol: Decimal, kmax: int, budget: list[int]) -> list[tuple[_Doc, ...]]:
    """Alle deelverzamelingen (grootte 2..kmax) met som(abs) binnen tol van target. Gesorteerd aflopend, met snoeien.
    budget[0] = resterende aantal knooppunten; bij 0 wordt gestopt (budget[1] = True bij afbreken)."""
    items = sorted(cands, key=lambda d: -abs(d.bedrag))
    amts = [abs(d.bedrag) for d in items]
    suffix = [ZERO] * (len(items) + 1)
    for i in range(len(items) - 1, -1, -1):
        suffix[i] = suffix[i + 1] + amts[i]
    res: list[tuple[_Doc, ...]] = []

    def rec(i: int, chosen: list[int], total: Decimal) -> None:
        if budget[0] <= 0:
            budget[1] = True
            return
        budget[0] -= 1
        if len(chosen) >= 2 and abs(total - target) <= tol:
            res.append(tuple(items[j] for j in chosen))
        if len(chosen) >= kmax or i >= len(items):
            return
        for j in range(i, len(items)):
            nt = total + amts[j]
            if nt > target + tol:
                continue                       # te groot: volgende (kleinere) proberen
            if nt + suffix[j + 1] < target - tol and len(chosen) + 1 + (len(items) - j - 1) >= 0:
                # zelfs met alle resterende kleinere posten wordt het doel niet gehaald
                if nt + sum(sorted(amts[j + 1:], reverse=True)[: kmax - len(chosen) - 1], ZERO) < target - tol:
                    continue
            rec(j + 1, chosen + [j], nt)
            if budget[0] <= 0:
                budget[1] = True
                return

    rec(0, [], ZERO)
    return res


def afpuntingsvoorstellen(items: Iterable[Any], soort: str = "debiteuren", tolerantie: float | Decimal = 0.05,
                          max_posten: int = 6, max_combinaties: int = 20_000, relatieoverschrijdend: bool = True,
                          ook_enkel_bedrag: bool = False, minimum_zekerheid: float = 0.0) -> dict:
    """Zoek voorstellen om negatieve posten (betalingen) aan facturen af te punten. Nooit schrijven."""
    if soort not in ("debiteuren", "crediteuren"):
        raise ValueError("soort moet 'debiteuren' of 'crediteuren' zijn")
    tol = D(tolerantie)
    if tol < 0:
        raise ValueError("tolerantie moet >= 0 zijn")
    kmax = max(2, min(int(max_posten), MAX_POSTEN_HARD))
    maxc = max(100, min(int(max_combinaties), MAX_COMBINATIES_HARD))
    docs = [_Doc(i + 1, it) for i, it in enumerate(items) if D(_get(it, "open_amount")) != 0]
    inv = [d for d in docs if d.bedrag > 0]
    pay = [d for d in docs if d.bedrag < 0]
    voorstellen: list[dict] = []
    afgebroken = False

    def add(typ: str, score: float, reden: list[str], betal: list[_Doc], fact: list[_Doc], actie: str, extra: Optional[dict] = None):
        sb = sum((abs(d.bedrag) for d in betal), ZERO)
        sf = sum((d.bedrag for d in fact), ZERO)
        rel = sorted({d.relatie for d in betal + fact})
        # datumcontrole: betaling ruim vóór factuurdatum is geen fout (voorschot) maar wel vermelden
        fd = [_d(_get(d.it, "date")) for d in fact if _d(_get(d.it, "date"))]
        bd = [_d(_get(d.it, "date")) for d in betal if _d(_get(d.it, "date"))]
        if fd and bd and max(bd) < min(fd):
            reden.append("betaling is van vóór de factuurdatum (mogelijk voorschot)")
            score -= 0.05
        score = round(max(0.05, min(0.99, score)), 2)
        v = {"type": typ, "zekerheid": score, "zekerheid_label": _label(score), "reden": reden, "relaties": rel,
             "documenten": [d.to_dict() for d in betal + fact], "som_betalingen": money(sb), "som_facturen": money(sf),
             "verschil": money(sf - sb), "voorgestelde_actie": actie, "_docs": {d.idx for d in betal + fact}}
        if extra:
            v.update(extra)
        voorstellen.append(v)

    afpunt_actie = ("Afpunten in Yuki (door de gebruiker of boekhouder): koppel de betaling(en) aan de factuur/facturen; "
                    "dit voorstel punt zelf niets af.")
    by_rel: dict[str, dict[str, list[_Doc]]] = {}
    for d in docs:
        by_rel.setdefault(d.rel_key(), {"inv": [], "pay": []})["inv" if d.bedrag > 0 else "pay"].append(d)

    # (a) 1-op-1, (b) n betalingen -> 1 factuur, (c) 1 betaling -> n facturen, binnen dezelfde relatie
    for key, g in by_rel.items():
        budget = [maxc, False]
        for p in g["pay"]:
            kand = [f for f in g["inv"] if abs(f.bedrag - abs(p.bedrag)) <= tol]
            for f in kand:
                exact = f.bedrag == abs(p.bedrag)
                s = 0.9 if exact else 0.8
                reden = ["zelfde relatie", "bedrag exact gelijk" if exact else f"bedrag binnen tolerantie (verschil {money(f.bedrag - abs(p.bedrag))})"]
                if p.tokens & f.tokens:
                    s += 0.08
                    reden.append("referentie komt overeen: " + ", ".join(sorted(p.tokens & f.tokens)))
                if len(kand) > 1:
                    s -= 0.1
                    reden.append(f"{len(kand)} facturen met hetzelfde bedrag: kies de juiste aan de hand van referentie of datum")
                add("1-op-1", s, reden, [p], [f], afpunt_actie)
        for f in g["inv"]:
            if len(g["pay"]) >= 2:
                for combo in _subsets(g["pay"], f.bedrag, tol, kmax, budget):
                    n = len(combo)
                    s = max(0.5, 0.78 - 0.04 * (n - 2))
                    reden = ["zelfde relatie", f"{n} betalingen samen = één factuur"]
                    if f.tokens & set().union(*[c.tokens for c in combo]):
                        s += 0.1
                        reden.append("referentie komt overeen")
                    add("meerdere-betalingen-een-factuur", s, reden, list(combo), [f], afpunt_actie + " Mogelijk een deelbetaling in schijven.")
        for p in g["pay"]:
            if len(g["inv"]) >= 2:
                for combo in _subsets(g["inv"], abs(p.bedrag), tol, kmax, budget):
                    n = len(combo)
                    s = max(0.5, 0.75 - 0.04 * (n - 2))
                    reden = ["zelfde relatie", f"één betaling = som van {n} facturen"]
                    if p.tokens & set().union(*[c.tokens for c in combo]):
                        s += 0.1
                        reden.append("referentie komt overeen")
                    add("een-betaling-meerdere-facturen", s, reden, [p], list(combo), afpunt_actie + " Mogelijk één overschrijving voor meerdere facturen.")
        afgebroken = afgebroken or budget[1]

    # (d) relatieoverschrijdend, lagere zekerheid
    if relatieoverschrijdend:
        for p in pay:
            for f in inv:
                if p.rel_key() == f.rel_key() or abs(f.bedrag - abs(p.bedrag)) > tol:
                    continue
                reden = ["ANDERE relatie dan de factuur", "bedrag " + ("exact gelijk" if f.bedrag == abs(p.bedrag) else "binnen tolerantie")]
                shared = p.tokens & f.tokens
                ratio = difflib.SequenceMatcher(None, p.naam, f.naam).ratio() if p.naam and f.naam else 0.0
                if p.naam and p.naam == f.naam:
                    s = 0.7
                    reden.append("zelfde relatienaam met verschillende relatiecode: mogelijk dubbele relatiefiche")
                    actie = ("Nagaan of beide relatiefiches dezelfde partij zijn; zo ja de fiches laten samenvoegen en daarna afpunten. "
                             "Anders navragen.")
                elif ratio >= 0.75:
                    s = 0.6
                    reden.append(f"gelijkaardige relatienaam (gelijkenis {ratio:.2f})")
                    actie = "Nagaan of het dezelfde partij is (andere schrijfwijze of dubbele fiche); zo ja afpunten na correctie van de relatie."
                elif shared:
                    s = 0.6
                    reden.append("zelfde referentie: " + ", ".join(sorted(shared)))
                    actie = "Betaling mogelijk op de verkeerde relatie geboekt: laten nakijken en verplaatsen of afpunten."
                elif ook_enkel_bedrag:
                    s = 0.25
                    reden.append("enkel het bedrag komt overeen (zwak signaal)")
                    actie = "Navragen: mogelijk toeval. Pas afpunten na bevestiging van relatie en referentie."
                else:
                    continue
                if shared and s < 0.7:
                    s += 0.05 if ratio >= 0.75 else 0
                add("relatieoverschrijdend", s, reden, [p], [f], actie)

    voorstellen = [v for v in voorstellen if v["zekerheid"] >= minimum_zekerheid]
    voorstellen.sort(key=lambda v: (-v["zekerheid"], v["type"], v["som_facturen"]))
    for i, v in enumerate(voorstellen, 1):
        v["id"] = f"V{i}"
    for v in voorstellen:
        v["overlapt_met"] = [w["id"] for w in voorstellen if w is not v and v["_docs"] & w["_docs"] and w["zekerheid"] >= v["zekerheid"]]
    gedekt = set()
    for v in voorstellen:
        if v["zekerheid"] >= DREMPEL_MAIL:
            gedekt |= v["_docs"]
    for v in voorstellen:
        del v["_docs"]
    zonder = [d for d in pay if d.idx not in gedekt]
    actie_zonder = ("Factuur opvragen bij de leverancier of laten bezorgen; daarna boeken en afpunten." if soort == "crediteuren"
                    else "Factuur nakijken: ontbreekt ze in de boekhouding of is ze nog niet gekoppeld? Zo nodig de factuur laten bezorgen.")
    return {
        "soort": soort, "tolerantie": float(tol), "max_posten_per_combinatie": kmax, "max_combinaties": maxc,
        "afgebroken": afgebroken,
        "samenvatting": {"negatieve_posten": len(pay), "open_facturen": len(inv), "voorstellen": len(voorstellen),
                         "hoog": sum(v["zekerheid_label"] == "hoog" for v in voorstellen),
                         "middel": sum(v["zekerheid_label"] == "middel" for v in voorstellen),
                         "laag": sum(v["zekerheid_label"] == "laag" for v in voorstellen),
                         "negatieve_posten_zonder_voorstel": len(zonder)},
        "voorstellen": voorstellen,
        "zonder_voorstel": [{**d.to_dict(), "voorgestelde_actie": actie_zonder} for d in zonder],
        "opmerking": ("Enkel voorstellen: er wordt niets afgepunt of gewijzigd in Yuki. Zekerheid is een inschatting op basis van bedrag, "
                      "relatie, referentie en datum; controleer elk voorstel."
                      + (" Zoekopdracht afgebroken: combinatielimiet bereikt, verhoog max_combinaties of beperk het dossier." if afgebroken else "")),
        "_gedekt": gedekt,
    }


def gedekte_sleutels(items: Iterable[Any], res: dict) -> set[str]:
    """Item-sleutels (item_key) van posten die in een voorstel met zekerheid >= DREMPEL_MAIL zitten."""
    docs = [_Doc(i + 1, it) for i, it in enumerate(items) if D(_get(it, "open_amount")) != 0]
    return {item_key(d.it) for d in docs if d.idx in res.get("_gedekt", set())}


def zonder_intern(res: dict) -> dict:
    return {k: v for k, v in res.items() if not k.startswith("_")}


def afpunting_csv_rijen(res: dict) -> list[list]:
    kop = ["voorstel", "type", "zekerheid", "label", "rol", "relatie", "referentie", "omschrijving", "datum", "vervaldatum", "bedrag",
           "verschil_voorstel", "reden", "voorgestelde_actie"]
    rows = [kop]
    for v in res["voorstellen"]:
        for d in v["documenten"]:
            rows.append([v["id"], v["type"], v["zekerheid"], v["zekerheid_label"], d["rol"], d["relatie"], d["referentie"] or "",
                         d["omschrijving"] or "", d["datum"] or "", d["vervaldatum"] or "", d["bedrag"], v["verschil"],
                         "; ".join(v["reden"]), v["voorgestelde_actie"]])
    for d in res["zonder_voorstel"]:
        rows.append(["-", "zonder voorstel", "", "", d["rol"], d["relatie"], d["referentie"] or "", d["omschrijving"] or "",
                     d["datum"] or "", d["vervaldatum"] or "", d["bedrag"], "", "negatief open bedrag zonder gevonden factuur", d["voorgestelde_actie"]])
    return rows
