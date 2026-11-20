"""Analyselaag: jaartotalen en ratio's per dossier en boekjaar (``yearly_totals.json``).

Rekent uitsluitend op data uit de bestaande leesmethodes (proef- en saldibalans
+ netto-omzet). Geen SOAP-calls in deze module: ``analyze_trial_balance`` is een
pure functie, zodat ze zonder Yuki te testen is.

Indeling volgens het Belgisch minimumrekeningenstelsel (MAR, KB 12/09/1983):

- 10–15, 19  eigen vermogen (19 = voorschot aan vennoten, verlaagt het EV)
- 16         voorzieningen en uitgestelde belastingen
- 17         schulden op meer dan één jaar
- 18         niet ingedeeld (bijkantoren/zetels)
- 20–28      vaste activa;  29 vorderingen op meer dan één jaar
- 3          voorraden en bestellingen in uitvoering
- 4          vorderingen én schulden op ten hoogste één jaar (beide zijden!)
             40/41 vorderingen, 42–48 schulden, 490/491 overlopende activa,
             492/493 overlopende passiva, 499 wachtrekeningen
- 5          liquide middelen (50–53 geldbeleggingen, 54–58 liquide middelen)
- 60–68      kosten;  69 resultaatverwerking
- 70–78      opbrengsten (70 = omzet);  79 resultaatverwerking
- 0, 8, 9    niet ingedeeld (buitenbalans / geen MAR-balansklasse)

Tekenconventie: saldo = debet − credit (positief = debetsaldo), zoals
``models.parse_gl_balance`` het oplevert.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Iterable, Literal, Mapping, Optional

from . import models

SCHEMA = "yuki.yearly_totals/v1"
FINANCIAL_MODES = {0: "commercieel", 1: "fiscaal"}
Klasse4Mode = Literal["saldo", "rubriek"]

_ZERO = Decimal(0)
_CENT = Decimal("0.01")
_RATIO_Q = Decimal("0.0001")

# Rubrieken waarin een saldo meetelt (sleutels van ``YearlyTotals.rubrieken``).
ACTIVA = ("vaste_activa", "vorderingen_lt", "voorraden", "vorderingen_kt",
          "overlopende_activa", "liquide_middelen")
PASSIVA = ("eigen_vermogen_klasse1", "voorzieningen", "schulden_lt", "schulden_kt",
           "overlopende_passiva")
RESULTAAT = ("kosten", "opbrengsten", "resultaatverwerking")


# ------------------------------------------------------------------ mapping
def account_digits(code: Optional[str]) -> str:
    """Leidende cijfers van een rekeningcode ("55.0000" → "550000", "4000-01" → "4000")."""
    out = []
    for ch in (code or "").strip():
        if ch.isdigit():
            out.append(ch)
        elif ch in ". " and out:
            continue
        else:
            break
    return "".join(out)


def mar_class(code: Optional[str]) -> Optional[int]:
    """MAR-klasse (0–9) van een rekeningcode, of ``None`` als de code niet numeriek begint."""
    d = account_digits(code)
    return int(d[0]) if d else None


def mar_nature(code: Optional[str]) -> str:
    """Rubriek volgens de MAR-nummering, los van het saldo.

    Mogelijke waarden: eigen_vermogen_klasse1, voorzieningen, schulden_lt,
    vaste_activa, vorderingen_lt, voorraden, vorderingen_kt, schulden_kt,
    overlopende_activa, overlopende_passiva, wachtrekening, geldbeleggingen,
    liquide_middelen, kosten, opbrengsten, resultaatverwerking, niet_ingedeeld.
    """
    d = account_digits(code)
    if not d:
        return "niet_ingedeeld"
    k, two = d[0], d[:2]
    if k == "1":
        if two in ("10", "11", "12", "13", "14", "15", "19"):
            return "eigen_vermogen_klasse1"
        if two == "16":
            return "voorzieningen"
        if two == "17":
            return "schulden_lt"
        return "niet_ingedeeld"  # 18 bijkantoren, of enkel "1"
    if k == "2":
        return "vorderingen_lt" if two == "29" else "vaste_activa"
    if k == "3":
        return "voorraden"
    if k == "4":
        if two in ("40", "41"):
            return "vorderingen_kt"
        if two == "49":
            three = d[:3]
            if three in ("490", "491"):
                return "overlopende_activa"
            if three in ("492", "493"):
                return "overlopende_passiva"
            return "wachtrekening"
        if len(d) >= 2:
            return "schulden_kt"  # 42–48
        return "wachtrekening"  # enkel "4": zijde onbekend → op saldo
    if k == "5":
        return "geldbeleggingen" if two in ("50", "51", "52", "53") else "liquide_middelen"
    if k == "6":
        return "resultaatverwerking" if two == "69" else "kosten"
    if k == "7":
        return "resultaatverwerking" if two == "79" else "opbrengsten"
    return "niet_ingedeeld"  # 0, 8, 9


def classify(code: Optional[str], saldo: Decimal, klasse4: Klasse4Mode = "saldo") -> str:
    """Rubriek waarin dit saldo meetelt in de jaartotalen.

    - Klasse 4 bevat beide zijden. ``klasse4="saldo"`` (standaard): debetsaldo →
      vorderingen KT (of overlopende activa voor 49x), creditsaldo → schulden KT
      (of overlopende passiva voor 49x). ``klasse4="rubriek"``: volg de MAR-nummering
      (40/41 actief, 42–48 passief, 490/1 resp. 492/3); 499 en onbekende codes
      blijven op saldo.
    - Klasse 5 met creditsaldo (kaskrediet) → schulden KT in modus ``saldo``.
    - Geldbeleggingen (50–53) tellen mee in liquide middelen (klasse 5).
    """
    nature = mar_nature(code)
    debit_side = saldo >= 0
    if nature in ("vorderingen_kt", "schulden_kt", "overlopende_activa",
                  "overlopende_passiva", "wachtrekening"):
        if klasse4 == "rubriek" and nature != "wachtrekening":
            return nature
        overlopend = nature.startswith("overlopende")
        if debit_side:
            return "overlopende_activa" if overlopend else "vorderingen_kt"
        return "overlopende_passiva" if overlopend else "schulden_kt"
    if nature in ("geldbeleggingen", "liquide_middelen"):
        if klasse4 == "saldo" and not debit_side:
            return "schulden_kt"
        return "liquide_middelen"
    return nature


# ------------------------------------------------------------------ helpers
def _amount(value: Decimal) -> float:
    return float(value.quantize(_CENT, rounding=ROUND_HALF_UP))


def _iso(value: date | datetime | str | None) -> Optional[str]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    if isinstance(value, date):
        return value.isoformat()
    return str(value)[:10]


def _line_value(line: Any, name: str) -> Any:
    return line.get(name) if isinstance(line, Mapping) else getattr(line, name, None)


def _dec(value: Any) -> Optional[Decimal]:
    if value is None or isinstance(value, Decimal):
        return value
    if isinstance(value, (int, float)):
        return Decimal(str(value))
    return models.to_decimal(str(value))


@dataclass(frozen=True)
class Ratio:
    naam: str
    formule: str
    teller: Decimal
    noemer: Optional[Decimal]
    waarde: Optional[Decimal]
    reden: Optional[str] = None
    opmerking: Optional[str] = None
    eenheid: str = "ratio"

    def to_dict(self) -> dict:
        if self.eenheid == "bedrag":
            waarde = _amount(self.waarde) if self.waarde is not None else None
        else:
            waarde = float(self.waarde.quantize(_RATIO_Q, rounding=ROUND_HALF_UP)) \
                if self.waarde is not None else None
        return {"waarde": waarde, "eenheid": self.eenheid, "formule": self.formule,
                "teller": _amount(self.teller),
                "noemer": _amount(self.noemer) if self.noemer is not None else None,
                "reden": self.reden, "opmerking": self.opmerking}


def _ratio(naam: str, formule: str, teller: Decimal, noemer: Decimal, noemer_label: str,
           opmerking: Optional[str] = None) -> Ratio:
    if noemer == 0:
        return Ratio(naam, formule, teller, noemer, None,
                     reden=f"deling door nul: {noemer_label} is 0")
    return Ratio(naam, formule, teller, noemer, teller / noemer, opmerking=opmerking)


# ------------------------------------------------------------------- result
@dataclass
class YearlyTotals:
    """Resultaat van de analyse; ``to_dict()`` is de ``yearly_totals.json``-vorm."""

    administration_id: Optional[str]
    administration_name: Optional[str]
    boekjaar: Optional[str]
    van: Optional[str]
    tot: Optional[str]
    financial_mode: int
    klasse4_mode: str
    bronnen: dict
    rubrieken: dict[str, Decimal]
    totals: dict[str, Decimal]
    ratios: dict[str, Ratio]
    klassen: dict[str, dict]
    controle: dict
    aannames: list[str]
    generated_at: str = field(default_factory=lambda: datetime.now(timezone.utc)
                              .replace(microsecond=0).isoformat())

    def to_dict(self) -> dict:
        from . import __version__
        return {
            "schema": SCHEMA,
            "generated_by": f"yuki-core {__version__}",
            "generated_at": self.generated_at,
            "dossier": {"administration_id": self.administration_id,
                        "name": self.administration_name},
            "boekjaar": {"label": self.boekjaar, "van": self.van, "tot": self.tot},
            "financial_mode": self.financial_mode,
            "financial_mode_label": FINANCIAL_MODES[self.financial_mode],
            "klasse4_mode": self.klasse4_mode,
            "bronnen": dict(self.bronnen),
            "totals": {k: _amount(v) for k, v in self.totals.items()},
            "ratios": {k: r.to_dict() for k, r in self.ratios.items()},
            "klassen": {k: {kk: (_amount(vv) if isinstance(vv, Decimal) else vv)
                            for kk, vv in v.items()} for k, v in self.klassen.items()},
            "controle": {k: (_amount(v) if isinstance(v, Decimal) else v)
                         for k, v in self.controle.items()},
            "aannames": list(self.aannames),
        }

    def to_json(self, indent: int = 2) -> str:
        return json.dumps(self.to_dict(), indent=indent, ensure_ascii=False)

    def write(self, path: Path | str) -> Path:
        """Schrijf ``yearly_totals.json`` naar ``path`` (alleen als de caller dat vraagt)."""
        p = Path(path).expanduser()
        if p.is_dir():
            p = p / "yearly_totals.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(self.to_json() + "\n", encoding="utf-8")
        return p


BASE_AANNAMES = (
    "MAR-indeling op de leidende cijfers van de rekeningcode (Belgisch minimumrekeningenstelsel).",
    "Saldo = debet − credit; positief is een debetsaldo (tekenconventie van de trial-balance parser).",
    "Proef- en saldibalans op de einddatum; resultaatrekeningen (6/7) bevatten enkel het lopende boekjaar.",
    "Eigen vermogen = klasse 10–15 en 19 + nog niet verwerkt resultaat (som van klasse 6 en 7, incl. 69/79).",
    "Nettoresultaat = opbrengsten 70–78 − kosten 60–68 (resultaatverwerking 69/79 niet meegeteld).",
    "Vlottende activa = 3 + 40/41 + 49x debet + klasse 5 (incl. geldbeleggingen 50–53); 29 (vorderingen > 1 jaar) niet.",
    "Schulden KT = 42–48 + 49x credit (incl. overlopende passiva 492/493).",
    "Vreemd vermogen = voorzieningen (16) + schulden LT (17) + schulden KT.",
    "ROA en ROE op eindsaldi van het boekjaar, niet op gemiddelden.",
    "financialMode is een aanname: 0 = commercieel (GLAccountBalance/NetRevenue), 1 = fiscaal (…Fiscal).",
)


def analyze_trial_balance(
    lines: Iterable[Any],
    *,
    net_revenue: Optional[Decimal | float | int | str] = None,
    financial_mode: int = 0,
    klasse4: Klasse4Mode = "saldo",
    administration_id: Optional[str] = None,
    administration_name: Optional[str] = None,
    boekjaar: Optional[str | int] = None,
    van: date | datetime | str | None = None,
    tot: date | datetime | str | None = None,
    bronnen: Optional[dict] = None,
    extra_aannames: Iterable[str] = (),
) -> YearlyTotals:
    """Bereken jaartotalen + ratio's uit proef- en saldibalanslijnen.

    ``lines``: ``models.GLLine``-objecten of dicts met ``code``/``debit``/``credit``/``balance``
    (zoals ``yuki_get_trial_balance`` teruggeeft). ``net_revenue``: bedrag uit
    ``NetRevenue``; ontbreekt het (of is het 0 terwijl klasse 70 niet 0 is), dan
    wordt klasse 70 gebruikt.
    """
    if financial_mode not in FINANCIAL_MODES:
        raise ValueError("financial_mode moet 0 (commercieel) of 1 (fiscaal) zijn")
    if klasse4 not in ("saldo", "rubriek"):
        raise ValueError("klasse4 moet 'saldo' of 'rubriek' zijn")

    rub: dict[str, Decimal] = {k: _ZERO for k in (*ACTIVA, *PASSIVA, *RESULTAAT, "niet_ingedeeld")}
    geldbeleggingen = omzet70 = kosten_6068 = opbrengsten_7078 = _ZERO
    klassen: dict[str, dict] = {}
    niet_ingedeeld: list[str] = []
    tegen_rubriek: list[str] = []
    wachtrekeningen: list[str] = []
    zonder_saldo = 0

    for line in lines:
        code = str(_line_value(line, "code") or "").strip()
        debit = _dec(_line_value(line, "debit"))
        credit = _dec(_line_value(line, "credit"))
        saldo = _dec(_line_value(line, "balance"))
        if saldo is None:
            if debit is None and credit is None:
                zonder_saldo += 1
                continue
            saldo = (debit or _ZERO) - (credit or _ZERO)

        k = mar_class(code)
        kkey = str(k) if k is not None else "?"
        agg = klassen.setdefault(kkey, {"debet": _ZERO, "credit": _ZERO, "saldo": _ZERO,
                                        "aantal_rekeningen": 0})
        agg["debet"] += debit if debit is not None else max(saldo, _ZERO)
        agg["credit"] += credit if credit is not None else max(-saldo, _ZERO)
        agg["saldo"] += saldo
        agg["aantal_rekeningen"] += 1

        nature = mar_nature(code)
        bucket = classify(code, saldo, klasse4)
        rub[bucket] += saldo
        if bucket == "niet_ingedeeld":
            if saldo != 0:
                niet_ingedeeld.append(code)
            continue
        if nature == "wachtrekening" and saldo != 0:
            wachtrekeningen.append(code)
        if saldo != 0 and ((nature in ("vorderingen_kt", "overlopende_activa") and saldo < 0)
                           or (nature in ("schulden_kt", "overlopende_passiva") and saldo > 0)
                           or (nature in ("geldbeleggingen", "liquide_middelen") and saldo < 0)):
            tegen_rubriek.append(code)
        if nature == "geldbeleggingen" and bucket == "liquide_middelen":
            geldbeleggingen += saldo
        d = account_digits(code)
        if nature == "opbrengsten":
            opbrengsten_7078 -= saldo
            if d[:2] == "70":
                omzet70 -= saldo
        elif nature == "kosten":
            kosten_6068 += saldo

    # Actief = debetsaldo; passief = creditsaldo (teken omdraaien).
    vaste = rub["vaste_activa"]
    vord_lt = rub["vorderingen_lt"]
    voorraden = rub["voorraden"]
    vord_kt = rub["vorderingen_kt"]
    overl_a = rub["overlopende_activa"]
    liquide = rub["liquide_middelen"]
    vlottend = voorraden + vord_kt + overl_a + liquide
    totaal_activa = vaste + vord_lt + vlottend

    ev_klasse1 = -rub["eigen_vermogen_klasse1"]
    resultaat_open = -(rub["kosten"] + rub["opbrengsten"] + rub["resultaatverwerking"])
    eigen_vermogen = ev_klasse1 + resultaat_open
    voorzieningen = -rub["voorzieningen"]
    schulden_lt = -rub["schulden_lt"]
    overl_p = -rub["overlopende_passiva"]
    schulden_kt = -rub["schulden_kt"] + overl_p
    vreemd = voorzieningen + schulden_lt + schulden_kt
    totaal_passiva = eigen_vermogen + vreemd
    netto = opbrengsten_7078 - kosten_6068

    aannames = list(BASE_AANNAMES)
    aannames.append(
        "Klasse 4 op saldo: debetsaldo → vorderingen KT, creditsaldo → schulden KT; "
        "klasse 5 met creditsaldo → schulden KT." if klasse4 == "saldo" else
        "Klasse 4 op MAR-rubriek: 40/41 actief, 42–48 passief, 490/1 en 492/3 overlopend; "
        "499 op saldo; klasse 5 altijd liquide middelen.")

    omzet_bron = "NetRevenue"
    nr = _dec(net_revenue)
    if nr is None:
        omzet, omzet_bron = omzet70, "klasse_70"
        aannames.append("Geen NetRevenue beschikbaar; omzet = creditsaldo van klasse 70.")
    elif nr == 0 and omzet70 != 0:
        omzet, omzet_bron = omzet70, "klasse_70"
        aannames.append("NetRevenue gaf 0 terwijl klasse 70 niet 0 is; omzet = klasse 70.")
    elif nr < 0 and omzet70 > 0:
        omzet = -nr
        aannames.append("NetRevenue was negatief (creditteken); teken omgedraaid.")
    else:
        omzet = nr
    aannames.extend(extra_aannames)

    ev_neg = "eigen vermogen is negatief; ratio niet zinvol te interpreteren" \
        if eigen_vermogen < 0 else None
    ratios = {
        "liquiditeit": _ratio("current ratio", "vlottende_activa / schulden_kt",
                              vlottend, schulden_kt, "schulden KT"),
        "solvabiliteit": _ratio("solvabiliteit", "eigen_vermogen / totaal_activa",
                                eigen_vermogen, totaal_activa, "totaal activa"),
        "debt_ratio": _ratio("debt ratio", "vreemd_vermogen / totaal_activa",
                             vreemd, totaal_activa, "totaal activa"),
        "working_capital": Ratio("werkkapitaal", "vlottende_activa - schulden_kt",
                                 vlottend, None, vlottend - schulden_kt, eenheid="bedrag"),
        "cash_ratio": _ratio("cash ratio", "liquide_middelen / schulden_kt",
                             liquide, schulden_kt, "schulden KT"),
        "net_margin": _ratio("nettomarge", "netto_resultaat / omzet", netto, omzet, "omzet"),
        "roa": _ratio("ROA", "netto_resultaat / totaal_activa", netto, totaal_activa, "totaal activa"),
        "roe": _ratio("ROE", "netto_resultaat / eigen_vermogen", netto, eigen_vermogen,
                      "eigen vermogen", opmerking=ev_neg),
    }

    totals = {
        "vaste_activa": vaste, "vorderingen_lt": vord_lt, "voorraden": voorraden,
        "vorderingen_kt": vord_kt, "overlopende_activa": overl_a,
        "liquide_middelen": liquide, "waarvan_geldbeleggingen": geldbeleggingen,
        "vlottende_activa": vlottend, "totaal_activa": totaal_activa,
        "eigen_vermogen_klasse1": ev_klasse1, "resultaat_niet_verwerkt": resultaat_open,
        "eigen_vermogen": eigen_vermogen, "voorzieningen": voorzieningen,
        "schulden_lt": schulden_lt, "schulden_kt": schulden_kt,
        "waarvan_overlopende_passiva": overl_p, "vreemd_vermogen": vreemd,
        "totaal_passiva": totaal_passiva,
        "kosten": kosten_6068, "opbrengsten": opbrengsten_7078,
        "omzet": omzet, "omzet_klasse_70": omzet70, "netto_resultaat": netto,
    }
    verschil = totaal_activa - totaal_passiva
    controle = {
        "balans_verschil": verschil,
        "in_evenwicht": abs(verschil) < _CENT,
        "niet_ingedeeld_saldo": -rub["niet_ingedeeld"],
        "niet_ingedeeld": sorted(niet_ingedeeld),
        "klasse4_5_tegen_rubriek": sorted(tegen_rubriek),
        "wachtrekeningen": sorted(wachtrekeningen),
        "lijnen_zonder_saldo": zonder_saldo,
        "omzet_bron": omzet_bron,
    }
    return YearlyTotals(
        administration_id=administration_id, administration_name=administration_name,
        boekjaar=str(boekjaar) if boekjaar is not None else None,
        van=_iso(van), tot=_iso(tot), financial_mode=financial_mode, klasse4_mode=klasse4,
        bronnen=dict(bronnen or {}), rubrieken=rub, totals=totals, ratios=ratios,
        klassen=dict(sorted(klassen.items())), controle=controle, aannames=aannames,
    )
