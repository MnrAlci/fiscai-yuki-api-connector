"""Boekingsworkflow (STANDAARD UIT). Eén item per keer, boekingsvoorstel, en pas na een expliciete bevestiging per boeking.

Wettelijke en praktische afbakening:
- Gebaseerd op het Belgische MAR (rekeningstelsel) en het Belgische btw-stelsel (tarieven 21/12/6/0). Voorgestelde rekeningen en btw-codes zijn
  voorstellen: verifieer in het rekeningschema van de administratie en 'verifieer actuele regel' voor wettelijke verwijzingen.
- Schrijft uitsluitend via de officieel gedocumenteerde methode Accounting.ProcessJournal (XML volgens https://www.yukiworks.nl/schemas/Journal.xsd,
  namespace urn:xmlns:http://www.theyukicompany.com:journal). Niet live getest: onzekerheden staan in docs/BOEKINGSWORKFLOW.md.
- Actief enkel met YUKI_WRITE_ENABLED=ja. Elke boeking vraagt een eenmalig bevestigingstoken, gebonden aan exact dat voorstel (hash),
  met vervaltijd. Geen bulk, geen auto-boeken. Elke poging komt in een lokaal auditlog (zonder sleutel).
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import tempfile
import time
from datetime import date, datetime, timezone
from decimal import ROUND_HALF_UP, Decimal
from pathlib import Path
from typing import Any, Optional
from xml.sax.saxutils import escape

from yuki_core.errors import YukiError
from yuki_core.paths import default_data_dir, secure_dir

from yuki_core import response_cache as _rc

from . import edition

try:                                   # alleen aanwezig in editie A
    from . import intern_boeking_regels
except ImportError:                    # editie B
    intern_boeking_regels = None

_rc.NEVER_CACHE.add("ProcessJournal")      # een schrijfcall wordt nooit uit of in de antwoordcache gehaald

if edition.INTERNAL_RULES:
    WORKFLOW_BLOK = ("Workflowdocumenten handel je af via yuki-core-afhandelen; een journaalpost geeft een dubbele kost. "
                     "ProcessJournal is alleen voor echte memoriaalposten (bron wachtrekening).")
else:
    WORKFLOW_BLOK = ("Workflowdocumenten handel je af in de Yuki-backoffice (knop 'Afhandelen'); een journaalpost geeft een dubbele kost. "
                     "ProcessJournal is alleen voor echte memoriaalposten (bron wachtrekening).")


def workflow_geblokkeerd(bron: Any, soort: Any) -> bool:
    """Harde blokkade: een workflowdocument (aankoop of verkoop) wordt nooit als journaalpost geboekt. Onbekend type van een workflowdocument telt ook als geblokkeerd."""
    return bron == "documentworkflow" and soort in (None, "", "aankoop", "verkoop")


NS = "urn:xmlns:http://www.theyukicompany.com:journal"
ENV_ENABLE = "YUKI_WRITE_ENABLED"
CENT = Decimal("0.01")
BTW_TARIEVEN = {"21": Decimal("0.21"), "12": Decimal("0.12"), "6": Decimal("0.06"), "0": Decimal("0")}   # Belgisch btw-stelsel; verifieer actuele regel
# Voorgestelde MAR-standaardrekeningen (voorstel; altijd controleren tegen het rekeningschema van de administratie).
STANDAARD = {"leverancier": "440000", "klant": "400000", "btw_aftrekbaar": "411000", "btw_verschuldigd": "451000"}
GROEPEN = {"aankoop": "MAR klasse 60 (handelsgoederen) of 61 (diensten en diverse goederen)", "verkoop": "MAR klasse 70 (omzet)"}
MAX_PER_DAG_STANDAARD = 25
TOKEN_TTL_STANDAARD_MIN = 15
VERIFIEER = "verifieer actuele regel"


def write_enabled() -> bool:
    return os.environ.get(ENV_ENABLE, "").strip().lower() == "ja"


def ttl_minuten() -> int:
    try:
        v = int(os.environ.get("YUKI_WRITE_TOKEN_TTL_MIN", TOKEN_TTL_STANDAARD_MIN))
    except ValueError:
        v = TOKEN_TTL_STANDAARD_MIN
    return max(1, min(v, 60))


def max_per_dag() -> int:
    try:
        v = int(os.environ.get("YUKI_WRITE_MAX_PER_DAY", MAX_PER_DAG_STANDAARD))
    except ValueError:
        v = MAX_PER_DAG_STANDAARD
    return max(1, min(v, 100))


def uit_tekst() -> dict:
    return {"actief": False,
            "uitleg": "De boekingsworkflow staat standaard UIT. Alleen de gebruiker kan ze aanzetten met de omgevingsvariabele "
                      f"{ENV_ENABLE}=ja (en elke boeking vraagt daarna nog een aparte, expliciete bevestiging). Er is niets gelezen of geschreven.",
            "documentatie": "docs/BOEKINGSWORKFLOW.md"}


# ------------------------------------------------------------------ lokale bestanden (0600)
def _dir() -> Path:
    return secure_dir(default_data_dir())


def _lees(naam: str, default: Any) -> Any:
    p = _dir() / naam
    try:
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else default
    except (OSError, ValueError):
        return default


def _schrijf(naam: str, data: Any) -> None:
    p = _dir() / naam
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def audit(rec: dict) -> None:
    """Auditlog: eigen bestand, alleen toevoegen, 0600; nooit sleutels of sessie-id's."""
    from .convert import scrub
    p = _dir() / "boekingen-audit.jsonl"
    rec = scrub({"tijd": datetime.now(timezone.utc).isoformat(timespec="seconds"), **rec})
    with open(p, "a", encoding="utf-8") as fh:
        fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
    os.chmod(p, 0o600)


def audit_lezen() -> list[dict]:
    p = _dir() / "boekingen-audit.jsonl"
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            out.append(json.loads(line))
        except ValueError:
            continue
    return out


def geboekt_vandaag() -> int:
    d = datetime.now(timezone.utc).date().isoformat()
    return sum(1 for r in audit_lezen() if r.get("uitkomst") == "geboekt" and str(r.get("tijd", "")).startswith(d))


# ------------------------------------------------------------------ voortgang (behandelde items)
def _state() -> dict:
    return _lees("boeking-state.json", {"behandeld": {}})


def behandeld(admin_id: str) -> dict:
    return _state()["behandeld"].get(admin_id, {})


def markeer(admin_id: str, item_id: str, status: str) -> None:
    s = _state()
    s["behandeld"].setdefault(admin_id, {})[item_id] = {"status": status, "tijd": datetime.now(timezone.utc).isoformat(timespec="seconds")}
    _schrijf("boeking-state.json", s)


# ------------------------------------------------------------------ bedragen en regels
def D(x: Any) -> Decimal:
    if x is None or x == "":
        raise ValueError("bedrag ontbreekt")
    return Decimal(str(x).replace(",", ".")).quantize(CENT, rounding=ROUND_HALF_UP)


def splits_btw(bedrag_incl: Decimal, btw_code: str, btw_bedrag: Optional[Decimal] = None) -> tuple[Decimal, Decimal]:
    """(netto, btw) uit het totaal incl. btw. Eigen btw_bedrag heeft voorrang (afrondingsverschillen op de factuur)."""
    if btw_bedrag is not None:
        return (bedrag_incl - btw_bedrag).quantize(CENT), btw_bedrag
    if btw_code not in BTW_TARIEVEN:
        raise ValueError("btw_code moet 21, 12, 6 of 0 zijn (Belgische tarieven; " + VERIFIEER + ")")
    p = BTW_TARIEVEN[btw_code]
    netto = (bedrag_incl / (1 + p)).quantize(CENT, rounding=ROUND_HALF_UP)
    return netto, (bedrag_incl - netto).quantize(CENT)


def regels_toepassen(omschrijving: str, relatie: str, categorie: str) -> dict:
    """Editie A: kantoorregels (btw-aftrek). Editie B: geen extra regels."""
    if edition.INTERNAL_RULES and intern_boeking_regels:
        return intern_boeking_regels.beoordeel(omschrijving, relatie, categorie)
    return {"btw_aftrekbaar": None, "notities": [], "regels": []}


class Regel:
    def __init__(self, rekening: str, bedrag: Decimal, omschrijving: str, datum: str, relatie: str = "", relatiecode: str = "", rol: str = "") -> None:
        self.rekening, self.bedrag, self.omschrijving, self.datum = str(rekening), bedrag, omschrijving[:256], datum
        self.relatie, self.relatiecode, self.rol = relatie, relatiecode, rol

    def xml(self) -> str:
        s = "<JournalEntry>"
        if self.relatie:
            s += f"<ContactName>{escape(self.relatie)}</ContactName>"
        if self.relatiecode:
            s += f"<ContactCode>{escape(self.relatiecode)}</ContactCode>"
        s += (f"<EntryDate>{self.datum}</EntryDate><GLAccount>{escape(self.rekening)}</GLAccount>"
              f"<Amount>{format(self.bedrag, 'f')}</Amount><Description>{escape(self.omschrijving)}</Description></JournalEntry>")
        return s

    def dict(self) -> dict:
        return {"rekening": self.rekening, "bedrag": float(self.bedrag), "kant": "debet" if self.bedrag > 0 else "credit", "omschrijving": self.omschrijving,
                "datum": self.datum, "relatie": self.relatie or None, "rol": self.rol}


def journal_xml(admin_id: str, onderwerp: str, regels: list[Regel]) -> str:
    """Journal-XML volgens het officiële schema (Journal.xsd). Valideert de documentatieregels lokaal."""
    valideer(regels)
    return (f'<Journal xmlns="{NS}"><AdministrationID>{escape(admin_id)}</AdministrationID>'
            f"<DocumentSubject>{escape(onderwerp[:200])}</DocumentSubject><JournalType>GeneralJournal</JournalType>"
            + "".join(r.xml() for r in regels) + "</Journal>")


def valideer(regels: list[Regel]) -> None:
    if len(regels) < 2:
        raise ValueError("Een journaal heeft minstens twee regels (Journal.xsd: minOccurs=2).")
    if sum((r.bedrag for r in regels), Decimal(0)) != 0:
        raise ValueError("De som van alle regels moet 0,00 zijn (Yuki weigert anders het hele bestand).")
    per_datum: dict[str, Decimal] = {}
    for r in regels:
        if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", r.datum):
            raise ValueError("Datum moet JJJJ-MM-DD zijn.")
        date.fromisoformat(r.datum)
        if not r.rekening.strip():
            raise ValueError("Elke regel heeft een grootboekrekening nodig.")
        if len(format(abs(r.bedrag), "f").replace(".", "")) > 12:
            raise ValueError("Bedrag te groot (maximaal 12 cijfers, 2 decimalen).")
        per_datum[r.datum] = per_datum.get(r.datum, Decimal(0)) + r.bedrag
    if any(v != 0 for v in per_datum.values()):
        raise ValueError("Het saldo per datum moet 0,00 zijn (Yuki weigert anders het hele bestand).")


def _tekst(v: Any, maxlen: int = 200) -> str:
    return re.sub(r"\s+", " ", str(v or "")).strip()[:maxlen]


# ------------------------------------------------------------------ btw-bedrag 0: reden verplicht
BTW_NUL_REDENEN = {
    "verlegd": ("verlegd (medecontractant)", True),
    "intracommunautair": ("intracommunautaire verwerving", True),
    "vrijgesteld": ("vrijgesteld", False),
    "buiten_toepassingsgebied": ("buiten toepassingsgebied", False),
    "kleine_onderneming": ("kleine onderneming/vrijstellingsregeling", False),
    "prive_niet_aftrekbaar": ("privé of niet-aftrekbaar", False),
    "ander": ("ander (toelichting verplicht)", False),
}
MIN_TOELICHTING = 5


def _reden_sleutel(raw: Any) -> Optional[str]:
    t = re.sub(r"[^a-z0-9]", "", str(raw or "").casefold())
    for k, (label, _) in BTW_NUL_REDENEN.items():
        if t in (re.sub(r"[^a-z0-9]", "", k), re.sub(r"[^a-z0-9]", "", label.casefold())):
            return k
    return None


def btw_nul(a: dict, datum: str, waarsch: list) -> dict:
    """Beoordeelt btw 0: reden verplicht; bij verlegging/IC-verwerving bevestigt de gebruiker de btw-regels zelf (niets wordt verzonnen)."""
    opties = ", ".join(f"{k} ({v[0]})" for k, v in BTW_NUL_REDENEN.items())
    sleutel = _reden_sleutel(a.get("btw_nul_reden"))
    if not sleutel:
        raise ValueError("btw_nul_reden: het btw-bedrag is 0 of ontbreekt; geef de reden op. Keuze: " + opties)
    label, gevolgen = BTW_NUL_REDENEN[sleutel]
    toel = _tekst(a.get("btw_nul_toelichting"), 120)
    if sleutel == "ander" and len(toel) < MIN_TOELICHTING:
        raise ValueError("btw_nul_toelichting: bij reden 'ander' is een toelichting verplicht (minstens 5 tekens)")
    waarsch.append(f"Btw 0 met reden '{label}'" + (f" ({toel})" if toel else "") + ": vastgelegd in omschrijving en auditlog; verifieer actuele regel.")
    extra: list[Regel] = []
    if gevolgen:
        waarsch.append("Bij " + label + " is de btw doorgaans zowel verschuldigd als aftrekbaar (beide in de btw-aangifte); verifieer actuele regel. "
                       "De plugin boekt die btw-regels niet automatisch: vul ze aan met 'btw_extra_regels' (lijst van rekening, bedrag, omschrijving; saldo 0) "
                       "en bevestig met 'btw_regels_bevestigd'=true, ook als u bewust geen btw-regels toevoegt.")
        if a.get("btw_regels_bevestigd") is not True:
            raise ValueError("btw_regels_bevestigd: bij " + label + " moet de gebruiker de btw-regels bevestigen of aanvullen (btw_extra_regels); er wordt niets automatisch verzonnen")
        tot = Decimal(0)
        for x in a.get("btw_extra_regels") or []:
            if not isinstance(x, dict):
                raise ValueError("btw_extra_regels: elk item is een object met rekening, bedrag en omschrijving")
            rek = _tekst(x.get("rekening"), 20)
            try:
                b = D(x.get("bedrag"))
            except Exception:
                raise ValueError("btw_extra_regels: ongeldig bedrag")
            if not rek or b == 0:
                raise ValueError("btw_extra_regels: rekening en bedrag (niet 0) zijn verplicht")
            tot += b
            extra.append(Regel(rek, b, _tekst(x.get("omschrijving"), 200) or f"btw {label}", datum, "", "", "btw (door gebruiker bevestigd)"))
        if tot != 0:
            raise ValueError("btw_extra_regels: de extra btw-regels moeten samen saldo 0,00 hebben")
        if len(extra) > 6:
            raise ValueError("btw_extra_regels: maximaal 6 regels")
    return {"sleutel": sleutel, "label": label, "toelichting": toel or None, "btw_gevolgen": gevolgen, "extra": extra,
            "btw_regels_bevestigd": a.get("btw_regels_bevestigd") is True}


def bouw_voorstel(item: dict, aanpass: dict, admin_id: str) -> dict:
    """item: {id, datum, omschrijving, bedrag(optioneel), relatie, referentie, bron}. aanpass: wijzigingen van de gebruiker."""
    a = {k: v for k, v in (aanpass or {}).items() if v not in (None, "")}
    kind = a.get("type") or ("bank" if item.get("bron") == "wachtrekening" else "aankoop")
    if kind not in ("aankoop", "verkoop", "bank"):
        raise ValueError("type moet aankoop, verkoop of bank zijn")
    datum = _tekst(a.get("datum") or item.get("datum"), 10)
    omschr = _tekst(a.get("omschrijving") or item.get("omschrijving") or item.get("referentie") or "Boeking", 250)
    relatie = _tekst(a.get("relatie") or item.get("relatie"), 120)
    relcode = _tekst(a.get("relatiecode"), 40)
    ref = _tekst(a.get("referentie") or item.get("referentie"), 60)
    categorie = _tekst(a.get("categorie"), 60)
    ontbrekend: list[str] = []
    waarsch: list[str] = [f"Voorstel gebaseerd op het Belgische MAR en btw-stelsel; controleer rekeningen en btw-code ({VERIFIEER})."]
    regels: list[Regel] = []
    toegepast = regels_toepassen(omschr, relatie, categorie)
    waarsch += toegepast["notities"]
    aftrek = a.get("btw_aftrek")
    if aftrek is None:
        aftrek = True if toegepast["btw_aftrekbaar"] is None else toegepast["btw_aftrekbaar"]
    elif toegepast["btw_aftrekbaar"] is False and aftrek:
        waarsch.append("Let op: een kantoorregel zegt dat hier geen btw-aftrek geldt; uw keuze 'btw_aftrek=true' is zonder uitleg afgewezen.")
        aftrek = False
    if not datum:
        ontbrekend.append("datum")
    try:
        if datum:
            date.fromisoformat(datum)
    except ValueError:
        ontbrekend.append("datum (JJJJ-MM-DD)")
        datum = ""
    bedrag_raw = a.get("bedrag_incl") if a.get("bedrag_incl") is not None else item.get("bedrag")
    try:
        gross = D(bedrag_raw) if bedrag_raw is not None else None
    except Exception:
        gross = None
    if gross is None or gross == 0:
        ontbrekend.append("bedrag_incl")
    rek = _tekst(a.get("rekening"), 20)
    if not rek:
        ontbrekend.append("rekening (" + (GROEPEN.get(kind, "doelrekening")) + ")")
    if kind in ("aankoop", "verkoop") and not relatie:
        ontbrekend.append("relatie")
    btw_code = str(a.get("btw_code", "")).strip()
    btw_bedrag = None
    bb_raw = a.get("btw_bedrag")
    if bb_raw in (None, "") and item.get("btw_bedrag") not in (None, ""):      # btw-bedrag uit het workflowdocument (VATAmount) als voorstel
        try:
            bb_raw = abs(D(item["btw_bedrag"]))
        except Exception:
            bb_raw = None
    if bb_raw not in (None, ""):
        try:
            btw_bedrag = D(bb_raw)
        except Exception:
            ontbrekend.append("btw_bedrag")
    if kind in ("aankoop", "verkoop") and not btw_code and btw_bedrag is None:
        ontbrekend.append("btw_code (21, 12, 6 of 0)")
    btw_info = None
    nul = None
    if not ontbrekend:
        try:
            if kind == "bank":
                wacht = _tekst(item.get("rekening_bron") or a.get("wachtrekening"), 20)
                if not wacht:
                    raise ValueError("wachtrekening onbekend")
                regels = [Regel(rek, gross, omschr, datum, relatie, relcode, "doelrekening"),
                          Regel(wacht, -gross, omschr, datum, "", "", "wachtrekening")]
            else:
                netto, btw = splits_btw(abs(gross), btw_code or "0", btw_bedrag)
                if btw < 0 or netto < 0:
                    raise ValueError("btw_bedrag kan niet groter zijn dan het totaal")
                btw_info = {"code": btw_code or "eigen bedrag", "netto": float(netto), "btw": float(btw), "aftrekbaar": bool(aftrek)}
                if btw == 0:
                    nul = btw_nul(a, datum, waarsch)
                    btw_info["nul_reden"] = nul["label"]
                teg = _tekst(a.get("tegenrekening"), 20) or STANDAARD["leverancier" if kind == "aankoop" else "klant"]
                if kind == "aankoop":
                    kost = netto + (btw if (not aftrek or btw == 0) else Decimal(0))
                    regels = [Regel(rek, kost, omschr, datum, "", "", "kost")]
                    if aftrek and btw != 0:
                        regels.append(Regel(_tekst(a.get("btw_rekening"), 20) or STANDAARD["btw_aftrekbaar"], btw, f"btw {omschr}", datum, "", "", "btw te vorderen"))
                    regels.append(Regel(teg, -(netto + btw), omschr + (f" ({ref})" if ref else ""), datum, relatie, relcode, "leverancier"))
                else:
                    regels = [Regel(teg, netto + btw, omschr + (f" ({ref})" if ref else ""), datum, relatie, relcode, "klant"),
                              Regel(rek, -netto, omschr, datum, "", "", "opbrengst")]
                    if btw != 0:
                        regels.append(Regel(_tekst(a.get("btw_rekening"), 20) or STANDAARD["btw_verschuldigd"], -btw, f"btw {omschr}", datum, "", "", "btw verschuldigd"))
            if nul:
                for r in regels:
                    if r.relatie:
                        r.omschrijving = (r.omschrijving + f" [btw 0: {nul['label']}" + (f", {nul['toelichting']}" if nul["toelichting"] else "") + "]")[:256]
                regels += nul["extra"]
            valideer(regels)
        except ValueError as e:
            ontbrekend.append(str(e))
            regels = []
    xml = journal_xml(admin_id, f"{omschr}"[:200], regels) if (regels and not ontbrekend) else None
    return {"type": kind, "volledig": xml is not None, "ontbrekend": ontbrekend, "waarschuwingen": waarsch, "regels_toegepast": toegepast["regels"],
            "btw": btw_info, "btw_nul": ({k: nul[k] for k in ("label", "toelichting", "btw_gevolgen", "btw_regels_bevestigd")} if nul else None), "boekingsregels": [r.dict() for r in regels], "journal_xml": xml,
            "tip": "Vul ontbrekende velden aan met 'aanpassingen' (rekening, btw_code, btw_aftrek, relatie, bedrag_incl, datum, omschrijving, type, categorie)." if ontbrekend else None}


def voorstel_hash(admin_id: str, xml: str) -> str:
    return hashlib.sha256(f"{admin_id}\n{xml}".encode("utf-8")).hexdigest()


# ------------------------------------------------------------------ tokens
def nieuw_token(admin_id: str, admin_name: str, item_id: str, bron: str, xml: str, samenvatting: list[dict], extra: Optional[dict] = None) -> dict:
    """Eén actief token per administratie: een nieuw voorstel maakt eerdere tokens ongeldig (geen bulk)."""
    tokens = _lees("boeking-tokens.json", {})
    nu = time.time()
    tokens = {t: v for t, v in tokens.items() if v["admin_id"] != admin_id and v["exp"] > nu and not v.get("gebruikt")}
    tok = secrets.token_urlsafe(18)
    h = voorstel_hash(admin_id, xml)
    tokens[tok] = {"admin_id": admin_id, "admin_name": admin_name, "item_id": item_id, "bron": bron, "xml": xml, "hash": h, "regels": samenvatting,
                   "exp": nu + ttl_minuten() * 60, "gebruikt": False, "extra": extra or {}}
    _schrijf("boeking-tokens.json", tokens)
    return {"bevestigingstoken": tok, "voorstel_hash": h, "geldig_minuten": ttl_minuten(),
            "vervalt_op": datetime.fromtimestamp(nu + ttl_minuten() * 60, timezone.utc).isoformat(timespec="seconds")}


def controleer_token(token: Any, admin_id: str, voorstel_hash_arg: Any) -> dict:
    if not isinstance(token, str) or not token or len(token) > 100:
        raise YukiError("Geef precies één bevestigingstoken (tekst). Meerdere boekingen tegelijk zijn niet mogelijk.")
    tokens = _lees("boeking-tokens.json", {})
    t = tokens.get(token)
    if not t:
        raise YukiError("Onbekend of reeds gebruikt bevestigingstoken: vraag een nieuw voorstel aan.")
    if t.get("gebruikt"):
        raise YukiError("Dit bevestigingstoken is al gebruikt (eenmalig). Vraag een nieuw voorstel aan.")
    if t["exp"] <= time.time():
        raise YukiError("Het bevestigingstoken is verlopen. Vraag een nieuw voorstel aan.")
    if t["admin_id"] != admin_id:
        raise YukiError("Dit token hoort bij een andere administratie dan in deze call.")
    if not isinstance(voorstel_hash_arg, str) or voorstel_hash_arg != t["hash"]:
        raise YukiError("voorstel_hash komt niet overeen met het voorstel waaraan het token gebonden is: het voorstel is gewijzigd of onbekend.")
    if voorstel_hash(t["admin_id"], t["xml"]) != t["hash"]:
        raise YukiError("Het opgeslagen voorstel is gewijzigd na het aanmaken van het token: geweigerd.")
    return t


def verbruik_token(token: str) -> None:
    tokens = _lees("boeking-tokens.json", {})
    if token in tokens:
        tokens[token]["gebruikt"] = True
        _schrijf("boeking-tokens.json", tokens)
