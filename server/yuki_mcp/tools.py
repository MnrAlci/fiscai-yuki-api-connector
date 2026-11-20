"""Toolimplementaties (standaard alleen lezen; boekingsworkflow uit). Elke tool: title, NL-beschrijving, object-inputschema, annotaties."""
from __future__ import annotations

import dataclasses
import json
import os
from datetime import date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any, Callable, Optional

from yuki_core import analysis
from yuki_core.errors import YukiDailyLimitReached, YukiError
from yuki_core.response_cache import ResponseCache

from . import afpunting as afp
from . import boeking
from . import dubbel
from . import afhandelen
from . import analytics as an
from . import opslag
from . import edition
from . import export as exp
from .attribution import ATTRIBUTION, ensure
from .clientfactory import ClientFactory
from .convert import MAX_ROWS, element_to_data, rows_of, scrub
from .handleiding import handleiding_md
from .limits import GRATIS_TEKST
from .mailconcept import bouw_concept
from .registry import G, GENERIC, P, all_methods, order_params
from .render import afpunting_html, dashboard_html, handleiding_html
from .transport import RawXml, is_allowed

UI_URI = "ui://yuki/dashboard.html"
ANN = {"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": True}


def obj(props: dict, required: list | None = None) -> dict:
    return {"type": "object", "properties": props, "required": required or [], "additionalProperties": False}


S = lambda d="", **k: {"type": "string", "description": d, **k}
I = lambda d="", **k: {"type": "integer", "description": d, **k}
B = lambda d="": {"type": "boolean", "description": d}
ADM = S("Administratie: naam of Administration ID (GUID). Zie yuki_administraties.")
DOM = S("Optioneel: domeinlabel. Kiest sleutel YUKI_ACCESS_KEY_<DOMEIN> als die bestaat en telt de calls op dat domein.")
VERN = B("Sla de antwoordcache over (kost een Yuki-call)")
SOORT = S("debiteuren of crediteuren", enum=["debiteuren", "crediteuren"])
EXPORT = S("Optioneel: map waarin een bestand wordt geschreven (alleen lokaal, op deze computer).")
OPSLAAN = B("Bewaar het resultaat in de door de gebruiker gekozen opslaglocatie (zie yuki_opslag_status). Alleen true zetten als de gebruiker dit in deze call vraagt; lokaal schrijven doet de plugin zelf, voor cloud krijgt u een voorstel en instructie, nooit een automatische upload.")
PAG_PROPS = {"alle_paginas": B("Haal alle pagina's op (standaard true)"), "max_paginas": I("Maximum aantal pagina's (standaard 20)"),
             "paginagrootte": I("Records per pagina (standaard 100)"), "start": I("Eerste record/pagina (standaard 0 of 1)")}


_AFP_VOORSTEL = ("Er {n_zijn} negatieve open posten (meestal betalingen zonder gekoppelde factuur). Wilt u een afpuntingscheck laten doen "
                 "met yuki_afpuntingsvoorstellen? Dat zoekt betalingen die bij een factuur horen, ook over relaties heen, zonder iets af te punten.")


def _afp_voorstel(n: int) -> str:
    return _AFP_VOORSTEL.replace("{n_zijn}", "is 1" if n == 1 else f"zijn {n}")


def creditor_sign() -> str:
    """Tekenaanname voor open crediteurenposten: 'positief' (standaard) of 'negatief' (te betalen = negatief)."""
    v = os.environ.get("YUKI_CREDITOR_SIGN", "positief").strip().lower()
    return "negatief" if v in ("negatief", "negative", "-") else "positief"


def _dt(v: Any) -> datetime:
    if isinstance(v, datetime):
        return v
    if isinstance(v, date):
        return datetime(v.year, v.month, v.day)
    return datetime.fromisoformat(str(v))


def _today() -> date:
    return date.today()


def afpunting_csv(out: dict) -> str:
    import csv
    import io
    from .attribution import ATTRIBUTION as _A
    buf = io.StringIO()
    w = csv.writer(buf, delimiter=";", lineterminator="\n")
    first = True
    for sd, r in out["resultaten"].items():
        rows = afp.afpunting_csv_rijen(r)
        for i, row in enumerate(rows):
            if i == 0 and not first:
                continue
            w.writerow([sd] + row if i else ["soort"] + row)
        first = False
    if edition.REQUIRE_ATTRIBUTION:
        w.writerow([])
        w.writerow([_A])
    return buf.getvalue()


def _jsonable(o: Any) -> Any:
    if isinstance(o, Decimal):
        return float(o)
    if isinstance(o, (datetime, date)):
        return o.isoformat()
    if hasattr(o, "__dataclass_fields__"):
        return {k: _jsonable(getattr(o, k)) for k in o.__dataclass_fields__ if k != "raw"}
    if isinstance(o, dict):
        return {k: _jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [_jsonable(v) for v in o]
    return o


_TYPES = {"string": str, "integer": int, "number": (int, float), "boolean": bool, "array": list, "object": dict}


def _validate_args(name: str, schema: dict, args: dict) -> None:
    """Eenvoudige invoercontrole tegen het inputSchema: verplicht, onbekend, type en enum. Duidelijke fout zonder waarden te echoën."""
    props = schema.get("properties") or {}
    miss = [r for r in schema.get("required", []) if args.get(r) in (None, "")]
    if miss:
        raise YukiError(f"{name}: ontbrekende parameter(s): {', '.join(miss)}.")
    unknown = [k for k in args if props and k not in props]
    if unknown:
        raise YukiError(f"{name}: onbekende parameter(s): {', '.join(sorted(unknown))}.")
    for k, v in args.items():
        spec = props.get(k) or {}
        want = _TYPES.get(spec.get("type"))
        if v is None or want is None:
            continue
        if spec["type"] in ("integer", "number") and isinstance(v, bool):
            raise YukiError(f"{name}: parameter '{k}' moet een getal zijn.")
        if spec["type"] == "integer" and isinstance(v, str) and v.strip().lstrip("-").isdigit():
            continue
        if spec["type"] == "boolean" and isinstance(v, str):
            continue                      # de afhandeling van tekstwaarden (bv. 'ja') blijft bij de tool zelf
        if not isinstance(v, want):
            raise YukiError(f"{name}: parameter '{k}' moet van het type {spec['type']} zijn.")
        if spec.get("enum") and v not in spec["enum"]:
            raise YukiError(f"{name}: parameter '{k}' heeft een ongeldige waarde; toegelaten: {', '.join(map(str, spec['enum']))}.")


class Tools:
    def __init__(self, factory: ClientFactory) -> None:
        self.f = factory
        self.defs: dict[str, dict] = {}
        self._current: dict[int, str] = {}
        self.handlers: dict[str, Callable[[dict], dict]] = {}
        self._build()

    # ----------------------------------------------------------- registratie
    def add(self, name: str, title: str, desc: str, schema: dict, fn: Callable[[dict], dict], meta: dict | None = None,
            ann: dict | None = None) -> None:
        d = {"name": name, "title": title, "description": desc, "inputSchema": schema, "annotations": {**(ann or ANN), "title": title}}
        if meta:
            d["_meta"] = meta
        self.defs[name] = d
        self.handlers[name] = fn

    def list(self) -> list[dict]:
        return list(self.defs.values())

    def call(self, name: str, args: dict | None) -> dict:
        if name not in self.handlers:
            raise YukiError(f"Onbekende tool: {name}")
        if args is not None and not isinstance(args, dict):
            raise YukiError("De argumenten moeten een JSON-object zijn.")
        _validate_args(name, self.defs[name]["inputSchema"], args or {})
        out = scrub(_jsonable(self.handlers[name](args or {})))
        return out

    # ------------------------------------------------------------ helpers
    def handle(self, a: dict):
        c = self.f.get(a.get("domein"))
        h = c.open_dossier(a["administratie"])
        h.force_refresh = bool(a.get("vernieuwen"))
        return h

    def _items(self, h, soort: str, peil: Optional[Any], normalize: bool = True) -> list:
        """Open posten. Voor analyses wordt het teken van crediteuren genormaliseerd naar
        'positief = nog te betalen' volgens YUKI_CREDITOR_SIGN (positief|negatief)."""
        items = h.open_items(soort, peildatum=peil)
        if normalize and soort == "crediteuren" and creditor_sign() == "negatief":
            items = [dataclasses.replace(i, open_amount=-i.open_amount if i.open_amount is not None else None,
                                         original_amount=-i.original_amount if i.original_amount is not None else None)
                     for i in items]
        return items

    def _pl(self, h, jaar: int, periode: str, bronnen: list) -> dict:
        s, e = an.periode_bereik(jaar, periode)
        end = h.trial_balance(e)
        bronnen.append(f"Accounting.GLAccountBalance(transactionDate={e.isoformat()})")
        prev = None
        if s != date(jaar, 1, 1):
            vd = s - timedelta(days=1)
            prev = h.trial_balance(vd)
            bronnen.append(f"Accounting.GLAccountBalance(transactionDate={vd.isoformat()})")
        return {"pl": an.pl_periode(end, prev), "van": s, "tot": e, "lines_end": end}

    # ------------------------------------------------------------- bouw
    def _build(self) -> None:
        f = self.f
        self.add("yuki_status", "Yuki-status en daglimiet",
                 "Dagteller per domein, ingestelde daglimiet (standaard 900), toegangsniveau en antwoordcache. "
                 + GRATIS_TEKST + " Instelbaar met YUKI_DAILY_LIMIT; boven 1000 alleen met YUKI_DAILY_LIMIT_APPROVAL en dan "
                 "kunnen kosten volgen. Doet zelf geen Yuki-call en toont geen geheimen of cijfers.",
                 obj({}), self._status)
        self.add("yuki_administraties", "Administraties", "Alle administraties die met de sleutel bereikbaar zijn.",
                 obj({"domein": DOM, "met_interne_klantcode": B(), "vernieuwen": VERN}), self._administraties)
        self.add("yuki_proefbalans", "Proef- en saldibalans",
                 "Saldo per grootboekrekening op een datum (Accounting.GLAccountBalance[Fiscal|YearEnd]). Saldo = debet - credit.",
                 obj({"administratie": ADM, "domein": DOM, "datum": S("Datum JJJJ-MM-DD"), "soort": S("commercieel, fiscaal of jaarafsluiting", enum=["commercieel", "fiscaal", "jaarafsluiting"]), "vernieuwen": VERN}, ["administratie", "datum"]), self._proefbalans)
        self.add("yuki_netto_omzet", "Netto-omzet", "Netto-omzet in een periode (Accounting.NetRevenue[Fiscal]).",
                 obj({"administratie": ADM, "domein": DOM, "van": S(), "tot": S(), "fiscaal": B(), "vernieuwen": VERN}, ["administratie", "van", "tot"]), self._omzet)
        self.add("yuki_openstaande_posten", "Openstaande posten",
                 "Openstaande debiteuren of crediteuren, optioneel op een peildatum (Accounting.Outstanding{Debtor|Creditor}Items[ByDateOutstanding]).",
                 obj({"administratie": ADM, "domein": DOM, "soort": SOORT, "peildatum": S("JJJJ-MM-DD, optioneel"), "vernieuwen": VERN}, ["administratie", "soort"]), self._open)
        self.add("yuki_grootboekmutaties", "Grootboekmutaties", "Boekingen op één grootboekrekening (AccountingInfo.GetTransactionDetails).",
                 obj({"administratie": ADM, "domein": DOM, "rekening": S(), "van": S(), "tot": S(), "fiscaal": B(), "vernieuwen": VERN}, ["administratie", "rekening", "van", "tot"]), self._mutaties)
        self.add("yuki_rekeningschema", "Rekeningschema", "Alle grootboekrekeningen (AccountingInfo.GetGLAccountScheme).",
                 obj({"administratie": ADM, "domein": DOM, "vernieuwen": VERN}, ["administratie"]), self._schema)
        self.add("yuki_boekjaar_gewijzigd", "Boekjaar laatst gewijzigd", "Laatste wijzigingsdatum van de boekingen in een boekjaar (AccountingInfo.GetFinancialYearModifiedDate).",
                 obj({"administratie": ADM, "domein": DOM, "jaar_id": I("Boekjaar-ID"), "vernieuwen": VERN}, ["administratie", "jaar_id"]), self._gewijzigd)
        self.add("yuki_jaartotalen", "Jaartotalen en ratio's", "Jaartotalen (MAR) en ratio's uit proef- en saldibalans en netto-omzet.",
                 obj({"administratie": ADM, "domein": DOM, "boekjaar": I(), "fiscaal": B(), "vernieuwen": VERN}, ["administratie", "boekjaar"]), self._jaartotalen)
        # analyses
        self.add("yuki_ouderdom_openstaande_posten", "Ouderdomsanalyse openstaande posten",
                 "Ouderdom (niet vervallen, 0-30, 31-60, 61-90, >90 dagen) van openstaande debiteuren/crediteuren; negatieve open bedragen apart (neutraal gelabeld, type enkel indien Yuki het meegeeft).",
                 obj({"administratie": ADM, "domein": DOM, "soort": SOORT, "peildatum": S("JJJJ-MM-DD, standaard vandaag"), "basis": S("vervaldatum of factuurdatum", enum=["vervaldatum", "factuurdatum"]), "vernieuwen": VERN}, ["administratie", "soort"]), self._ouderdom)
        self.add("yuki_dso_dpo", "DSO en DPO", "Gemiddelde betaaltermijn: DSO = debiteuren/omzet x dagen, DPO = crediteuren/inkopen (klasse 60) x dagen, vanaf 1 januari.",
                 obj({"administratie": ADM, "domein": DOM, "jaar": I(), "tot": S("JJJJ-MM-DD, standaard vandaag of 31/12"), "btw_percentage": {"type": "number", "description": "Optionele btw-correctie op omzet/inkopen, bv. 21"}, "vernieuwen": VERN}, ["administratie", "jaar"]), self._dso)
        self.add("yuki_top_relaties", "Top debiteuren of crediteuren", "Grootste openstaande saldi per relatie.",
                 obj({"administratie": ADM, "domein": DOM, "soort": SOORT, "aantal": I("Standaard 10"), "peildatum": S(), "vernieuwen": VERN}, ["administratie", "soort"]), self._top)
        self.add("yuki_periodevergelijking", "Periodevergelijking", "Omzet, kosten en resultaat voor een maand, kwartaal of jaar, vergeleken met de vorige periode en/of hetzelfde van vorig jaar.",
                 obj({"administratie": ADM, "domein": DOM, "jaar": I(), "periode": S("jaar, kwartaal:1-4 of maand:1-12"), "vergelijk_met": S("vorige_periode, vorig_jaar of beide", enum=["vorige_periode", "vorig_jaar", "beide"]), "vernieuwen": VERN}, ["administratie", "jaar", "periode"]), self._vergelijk)
        self.add("yuki_marge_kostenstructuur", "Marge en kostenstructuur", "Brutomarge, nettomarge en kosten per MAR-klasse (60-68) in een periode.",
                 obj({"administratie": ADM, "domein": DOM, "jaar": I(), "periode": S("jaar, kwartaal:n of maand:n (standaard jaar)"), "vernieuwen": VERN}, ["administratie", "jaar"]), self._marge)
        self.add("yuki_liquiditeit", "Liquiditeitsratio's", "Current ratio, cash ratio, werkkapitaal, solvabiliteit op een datum.",
                 obj({"administratie": ADM, "domein": DOM, "datum": S(), "vernieuwen": VERN}, ["administratie", "datum"]), self._liq)
        self.add("yuki_uitschieters", "Uitschieters in het grootboek", "Statistische uitschieters (mediaan/MAD) en mogelijk dubbele boekingen op één grootboekrekening. Geen oordeel: laat nakijken door de boekhouder.",
                 obj({"administratie": ADM, "domein": DOM, "rekening": S(), "van": S(), "tot": S(), "drempel": {"type": "number"}, "vernieuwen": VERN}, ["administratie", "rekening", "van", "tot"]), self._uitschieters)
        self.add("yuki_dashboard", "Dashboard", "Dashboard met omzet, kosten, resultaat, liquiditeit, openstaande debiteuren/crediteuren met ouderdom en btw-saldo-indicatie. Toont een widget en schrijft optioneel een HTML-export.",
                 obj({"administratie": ADM, "domein": DOM, "jaar": I(), "periode": S("jaar, kwartaal:n of maand:n"), "peildatum": S(), "export_map": EXPORT, "opslaan": OPSLAAN, "vernieuwen": VERN}, ["administratie", "jaar"]),
                 self._dashboard, meta={"ui": {"resourceUri": UI_URI}, "ui/resourceUri": UI_URI})
        self.add("yuki_export_dataset", "Export naar CSV, Excel, JSON of Parquet",
                 "Schrijft een dataset met vast, gedocumenteerd schema (kpis, saldi, openstaande_posten) als lokaal bestand in een map naar keuze, voor Power BI, Qlik, Tableau, Metabase, Excel enz. Formaten: csv, json, xlsx (zonder extra bibliotheek) en parquet (vraagt pyarrow). Alleen lezen in Yuki; schrijft enkel naar uw map. Zonder export_map krijgt u alleen schema en een voorbeeldregel terug.",
                 obj({"dataset": S("kpis, saldi of openstaande_posten", enum=list(exp.SCHEMAS)), "administratie": ADM, "domein": DOM, "jaar": I("Voor kpis en saldi (boekjaar)"),
                      "periode": S("jaar, kwartaal:n of maand:n (standaard jaar)"), "peildatum": S("JJJJ-MM-DD (standaard einde periode of vandaag)"),
                      "soort": S("Voor openstaande_posten: debiteuren of crediteuren", enum=["debiteuren", "crediteuren"]),
                      "formaten": {"type": "array", "items": {"type": "string", "enum": list(exp.FORMATS)}, "description": "Standaard csv en json"},
                      "export_map": S("Map voor de bestanden (bv. ~/yuki-export). Leeg = alleen schema en voorbeeld."), "vernieuwen": VERN}, ["dataset", "administratie"]), self._export_dataset)
        self.add("yuki_dossier_transfer_export", "Dossieroverdracht per boekjaar (export voor de volgende boekhouder)",
                 "Exporteert per boekjaar naar een map: rekeningschema, proefbalans (slot, begin, jaarafsluiting), startbalans, grootboekmutaties, openstaande posten op balansdatum, contacten, btw-gegevens, klasse-2-saldi (indicatie) en optioneel documentmetadata; "
                 "met MANIFEST.json (SHA-256), CONTROL.md (afstemmingen) en README voor de ontvanger. Alleen lezen voor Yuki; schrijft lokale bestanden. Schat eerst het aantal calls: boven de drempel (standaard 150) of boven het resterende daglimiet is 'bevestig' nodig. "
                 "Hervat via een checkpoint in de map. Beperkingen van de API (geen boekjarenlijst, geen dagboekcode, geen activaregister, geen documentinhoud): verifieer actuele regel; zie docs/DOSSIER-TRANSFER.md.",
                 obj({"administratie": ADM, "domein": DOM, "jaren": {"type": "array", "items": {"type": "integer"}, "description": "Boekjaren (jaartal waarin het boekjaar begint), bv. [2024, 2025]"},
                      "alle_jaren": B("Alle jaren vanaf eerste_jaar (standaard huidig jaar min 5) tot en met het huidige jaar"), "eerste_jaar": I("Eerste jaar bij alle_jaren"),
                      "export_map": S("Doelmap (verplicht)"), "zip": B("Maak per jaar ook een zip"), "inclusief_documenten": B("Ook documentmetadata uit het archief (geen bestandsinhoud)"),
                      "alle_rekeningen": B("Haal mutaties van elke rekening op, niet alleen rekeningen met saldo (meer calls)"), "start_maand_boekjaar": I("Eerste maand van het boekjaar (1 tot 12, standaard 1)"),
                      "formaten": {"type": "array", "items": {"type": "string", "enum": ["csv", "json", "xlsx"]}, "description": "Standaard csv en json"},
                      "alleen_schatting": B("Alleen het aantal calls schatten (1 à 2 calls), niets exporteren"), "bevestig": B("Bevestiging van de gebruiker na de schatting"),
                      "drempel": I("Drempel voor bevestiging in calls (standaard 150)"), "hervat": B("Hervat vanaf het checkpoint (standaard ja)"),
                      "debiteurenprefix": S("Rekeningprefix debiteuren voor de controle (standaard 40)"), "crediteurenprefix": S("Rekeningprefix crediteuren voor de controle (standaard 44)")}, ["administratie", "export_map"]),
                 self._dossier_transfer)
        self.add("yuki_dashboard_kpis", "Kerncijfers (compact, ondernemer)",
                 "Compacte kerncijfers van één administratie voor een eigen dashboard: omzet, kosten, resultaat, marge, liquide middelen, liquiditeit, open debiteuren en crediteuren (totaal en vervallen), DSO/DPO, btw-saldo-indicatie en optioneel de vergelijking met de vorige periode. Bundelt bestaande leesmethodes; alleen lezen, geen advies.",
                 obj({"administratie": ADM, "domein": DOM, "jaar": I(), "periode": S("jaar, kwartaal:n of maand:n (standaard jaar)"), "peildatum": S("Optioneel, JJJJ-MM-DD"),
                      "vergelijk_vorige_periode": B("Vergelijk met de vorige periode (kost 1 à 2 extra Yuki-calls)"), "vernieuwen": VERN}, ["administratie", "jaar"]), self._dashboard_kpis)
        self.add("yuki_portfolio_kpis", "Kerncijfers per administratie (portfolio, accountant)",
                 "Kerncijfers per administratie over meerdere dossiers heen (omzet, kosten, resultaat, liquide middelen, open debiteuren en crediteuren) voor een portfolio-overzicht. Kost ongeveer 4 Yuki-calls per administratie; standaard hoogstens 5 administraties, maximum 15. Een fout bij één dossier stopt de rest niet. Alleen lezen, geen advies; deel geen klantgegevens met derden.",
                 obj({"administraties": {"type": "array", "items": {"type": "string"}, "description": "Namen of GUID's van administraties (zie yuki_administraties). Leeg = de eerste max_administraties."},
                      "domein": DOM, "jaar": I(), "periode": S("jaar, kwartaal:n of maand:n (standaard jaar)"), "peildatum": S("Optioneel, JJJJ-MM-DD"),
                      "max_administraties": {"type": "integer", "description": "Standaard 5, maximum 15"}, "vernieuwen": VERN}, ["jaar"]), self._portfolio_kpis)
        self.add("yuki_herinneringsmail", "Herinneringsmail (concept)", "Bouwt een CONCEPTmail voor één relatie met openstaande posten. Verstuurt nooit iets; optioneel een .eml in een map.",
                 obj({"administratie": ADM, "domein": DOM, "relatie": S("Naam of deel van de naam van de relatie"), "soort": SOORT, "peildatum": S(), "aanspreekvorm": S("u of je", enum=["u", "je"]), "aanhef": S(), "handtekening": S(), "aan": S("Optioneel e-mailadres van de ontvanger"), "cc": S(), "eml_map": EXPORT, "opslaan": OPSLAAN, "vernieuwen": VERN}, ["administratie", "relatie", "soort"]), self._mail)
        self.add("yuki_handleiding_saldi", "Handleiding saldi", "Uitleg over positieve en negatieve saldi bij debiteuren en crediteuren en wat te doen. Optioneel als .md en .html in een map.",
                 obj({"export_map": EXPORT, "administratie": S("Optioneel: nodig voor opslaan=true (bepaalt de opslaglocatie)."), "opslaan": OPSLAAN}), self._handleiding)
        self.add("yuki_afpuntingsvoorstellen", "Afpuntingsvoorstellen",
                 "Zoekt voorstellen om negatieve open posten (meestal betalingen zonder gekoppelde factuur) af te punten: 1-op-1 (gelijk bedrag of binnen tolerantie), "
                 "meerdere betalingen voor één factuur, één betaling voor meerdere facturen en lagere-zekerheidsvoorstellen over verschillende of gelijkaardige "
                 "relaties heen (o.a. dubbele relatiefiche). Per voorstel: relaties, documenten, datums, bedragen, verschil, zekerheid met reden en voorgestelde actie. "
                 "Alleen voorstellen: er wordt niets afgepunt (Yuki blijft alleen-lezen). Stel de gebruiker voor deze afpuntingscheck te doen als er negatieve posten zijn. "
                 "Export als CSV en HTML met export_map.",
                 obj({"administratie": ADM, "domein": DOM, "soort": S("debiteuren, crediteuren of beide (standaard beide)", enum=["debiteuren", "crediteuren", "beide"]),
                      "peildatum": S("JJJJ-MM-DD, optioneel"), "tolerantie": {"type": "number", "description": "Toegelaten bedragsverschil in euro (standaard 0,05)"},
                      "max_posten": I("Maximum aantal posten per combinatie (standaard 6, maximum 8)"),
                      "max_combinaties": I("Maximum aantal onderzochte combinaties per relatie (standaard 20000, maximum 200000)"),
                      "relatieoverschrijdend": B("Zoek ook over verschillende relaties heen (standaard true; lagere zekerheid)"),
                      "ook_enkel_bedrag": B("Neem ook relatieoverschrijdende treffers op waar enkel het bedrag overeenkomt (zeer lage zekerheid; standaard false)"),
                      "minimum_zekerheid": {"type": "number", "description": "Toon enkel voorstellen met zekerheid >= deze waarde (0 tot 1)"},
                      "export_map": EXPORT, "opslaan": OPSLAAN, "vernieuwen": VERN}, ["administratie"]), self._afpunting)
        self.add("yuki_opslag_status", "Opslaglocatie: status",
                 "Toont welke opslaglocatie de gebruiker koos voor het permanente dossier (per administratie) en welke koppeling daarvoor nodig is. "
                 "Zonder keuze krijgt u de vraag en de opties; er is geen standaardlocatie. Doet geen Yuki-call.",
                 obj({"administratie": S("Optioneel: administratie (naam)")}), self._opslag_status,
                 ann={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
        self.add("yuki_opslag_instellen", "Opslaglocatie: instellen",
                 "Bewaart de keuze van de gebruiker voor het permanente dossier in de lokale configuratie (per administratie, of voor alle administraties "
                 "als de gebruiker dat uitdrukkelijk vraagt met administratie='*'). Types: lokaal, onedrive, sharepoint, google_drive, dropbox, dossierbeheer, geen. "
                 "Geeft de benodigde koppeling met installatie-uitleg en markeert wat betalend kan zijn. Wijzigt enkel de lokale config; niets in Yuki, niets geüpload. "
                 "Zonder 'type' krijgt u de vraag terug.",
                 obj({"administratie": S("Administratie (naam) of '*' voor alle administraties (alleen op uitdrukkelijk verzoek van de gebruiker)"),
                      "type": S("Gekozen opslagtype", enum=list(opslag.TYPES)),
                      "pad": S("Voor 'lokaal': absoluut pad van de map"),
                      "sync_map": S("Voor cloud: optioneel absoluut pad van de lokaal gesynchroniseerde map; de plugin schrijft dan lokaal en uw sync-app uploadt"),
                      "doelpad": S("Voor cloud: optioneel pad/mapnaam in de cloud, enkel voor het opslagvoorstel"),
                      "wissen": B("Verwijder de bewaarde keuze")}), self._opslag_instellen,
                 ann={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
        self._add_boeking()
        for g in GENERIC:
            self._add_generic(g)

    # ----------------------------------------------------- boekingsworkflow (standaard UIT)
    def _add_boeking(self) -> None:
        uit = " STANDAARD UIT: werkt alleen met YUKI_WRITE_ENABLED=ja."
        item = {"administratie": ADM, "domein": DOM,
                "bron": S("wachtrekening (niet-verwerkte bankverrichtingen op de wachtrekening) of documentworkflow (documenten in een archiefmap)", enum=["wachtrekening", "documentworkflow"]),
                "wachtrekening": S("Voor bron=wachtrekening: code van de wachtrekening in het rekeningschema (bv. MAR 499; eerst controleren met yuki_rekeningschema)"),
                "map_id": I("Voor bron=documentworkflow: archiefmap-ID (zie yuki_archief_mappen)"),
                "van": S("JJJJ-MM-DD, standaard 1 januari van dit jaar"), "tot": S("JJJJ-MM-DD, standaard vandaag"), "vernieuwen": VERN}
        self.add("yuki_boeking_voorstel", "Boeking: volgend item en voorstel",
                 "Toont het volgende onbehandelde item (document uit de documentworkflow of bankverrichting op de wachtrekening) met een boekingsvoorstel "
                 "(rekening, btw-code, relatie, bedrag, omschrijving; Belgisch MAR en btw-stelsel). Met item_id en aanpassingen krijgt u een bijgewerkt voorstel. "
                 "Boekt NIETS. Voor workflowdocumenten (aankoop of verkoop) geeft het nooit een token: die handel je af in de Yuki-backoffice (knop 'Afhandelen'). Controleert eerst op een bestaande boeking (GetTransactionDetails rond de documentdatum): bij 'mogelijk al geboekt', 'al geboekt' of een mislukte controle is het item geblokkeerd (geen token) tenzij deblokkeren=true met deblokkeer_reden. Anders een eenmalig bevestigingstoken (met vervaltijd) gebonden aan exact dit voorstel." + uit,
                 obj({**item, "item_id": S("Optioneel: een bepaald item (anders het volgende)"),
                      "deblokkeren": B("Alleen na uitdrukkelijke keuze van de gebruiker: een door de dubbelcontrole geblokkeerd item toch voorstellen (vereist deblokkeer_reden; komt in het auditlog)"),
                      "deblokkeer_reden": S("Reden voor het deblokkeren (minstens 10 tekens)"),
                      "aanpassingen": {"type": "object", "description": "Wijzigingen: type (aankoop|verkoop|bank), rekening, tegenrekening, btw_code (21|12|6|0), btw_bedrag, btw_nul_reden (verplicht bij btw 0: verlegd|intracommunautair|vrijgesteld|buiten_toepassingsgebied|kleine_onderneming|prive_niet_aftrekbaar|ander), btw_nul_toelichting (verplicht bij ander), btw_regels_bevestigd (verplicht bij verlegd/intracommunautair), btw_extra_regels (lijst {rekening,bedrag,omschrijving}, saldo 0), btw_aftrek (bool), btw_rekening, relatie, relatiecode, bedrag_incl, datum, omschrijving, referentie, categorie",
                                       "additionalProperties": {"type": ["string", "number", "boolean", "array"]}}}, ["administratie", "bron"]),
                 self._boek_voorstel, ann={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": False, "openWorldHint": True})
        self.add("yuki_boeking_overslaan", "Boeking: item overslaan",
                 "Markeert een item lokaal als overgeslagen zodat het niet meer als volgend item verschijnt. Schrijft niets in Yuki." + uit,
                 obj({"administratie": ADM, "domein": DOM, "item_id": S("Item-ID uit yuki_boeking_voorstel")}, ["administratie", "item_id"]),
                 self._boek_overslaan, ann={"readOnlyHint": False, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})
        self.add("yuki_boeking_bevestigen", "Boeking: bevestigen (schrijft in Yuki)",
                 "SCHRIJFT één journaalpost in Yuki (Accounting.ProcessJournal) na uitdrukkelijke bevestiging van de gebruiker voor precies dit voorstel. "
                 "Vereist het eenmalige token en de voorstel_hash uit yuki_boeking_voorstel en bevestiging='ja'. Geen bulk: één token, één boeking. "
                 "Met dry_run=true ziet u de exacte XML zonder te boeken (token blijft geldig). Telt mee in de daglimiet en komt in het lokale auditlog." + uit,
                 obj({"administratie": ADM, "domein": DOM, "token": S("Het bevestigingstoken van dit ene voorstel"),
                      "voorstel_hash": S("De voorstel_hash van dat voorstel"),
                      "bevestiging": S("Moet 'ja' zijn: de gebruiker bevestigt uitdrukkelijk deze ene boeking", enum=["ja"]),
                      "dry_run": B("Toon de exacte XML zonder te boeken")}, ["administratie", "token", "voorstel_hash"]),
                 self._boek_bevestigen, ann={"readOnlyHint": False, "destructiveHint": True, "idempotentHint": False, "openWorldHint": True})
        self.add("yuki_afhandeling_controle", "Controle na afhandelen in de backoffice",
                 "Leest Backoffice.GetWorkflow en controleert of een document (document_id uit het boekingsvoorstel, 'D:<id>') niet meer in de workflow staat, "
                 "nadat het in de Yuki-backoffice is afgehandeld. Alleen lezen; kost 1 call (vernieuwt standaard). Het antwoordformaat van GetWorkflow is niet gedocumenteerd: bij twijfel 'onbepaald'.",
                 obj({"administratie": ADM, "domein": DOM, "document_id": S("Document-ID, bv. 'D:<id>' uit het voorstel"), "vernieuwen": VERN}, ["administratie", "document_id"]),
                 self._afhandeling_controle)
        self.add("yuki_boeking_status", "Boeking: status",
                 "Toont of de boekingsworkflow aanstaat, de vervaltijd van tokens, het dagmaximum en het aantal boekingen vandaag. Geen Yuki-call, geen bedragen.",
                 obj({}), self._boek_status, ann={"readOnlyHint": True, "destructiveHint": False, "idempotentHint": True, "openWorldHint": False})

    def _afhandeling_controle(self, a):
        try:
            doc = afhandelen.document_id(a.get("document_id"))
            afhandelen.beoordeel([], doc)                       # valideert het ID vóór er een call vertrekt
        except ValueError as e:
            raise YukiError(str(e))
        g = next(x for x in GENERIC if x.tool == "yuki_backoffice_workflow")
        res = self._run_generic(g, {"administratie": a["administratie"], "domein": a.get("domein"), "vernieuwen": a.get("vernieuwen", True)})
        out = afhandelen.beoordeel(res.get("gegevens"), doc)
        out.update({"methode": res.get("methode"), "document_id": doc, "opmerking": "Alleen lezen. De afhandeling zelf gebeurt in de Yuki-backoffice (knop 'Afhandelen'); deze controle bevestigt enkel dat het document uit GetWorkflow verdwenen is."})
        return out

    def _boek_items(self, h, a: dict) -> list[dict]:
        if a["bron"] == "wachtrekening":
            if not a.get("wachtrekening"):
                raise YukiError("Geef 'wachtrekening' (code uit uw rekeningschema, zie yuki_rekeningschema).")
            van = a.get("van") or date(_today().year, 1, 1).isoformat()
            tot = a.get("tot") or _today().isoformat()
            txs = [t for t in h.gl_transactions(a["wachtrekening"], van, tot) if t.amount]
            vrij: dict[Decimal, list] = {}
            for t in sorted(txs, key=lambda x: (x.date or datetime.min, x.id or "")):
                vrij.setdefault(-t.amount, []).append(t)
            weg: set = set()
            for t in txs:                           # reeds tegengeboekt (gelijk en tegengesteld bedrag): niet voorstellen
                lst = vrij.get(t.amount) or []
                lst = [x for x in lst if x.id not in weg and x.id != t.id]
                if lst and t.id not in weg:
                    weg.add(t.id)
                    weg.add(lst[0].id)
            return [{"id": f"W:{t.id}", "bron": "wachtrekening", "datum": (t.date.date().isoformat() if t.date else None), "omschrijving": t.description,
                     "bedrag": str(t.amount), "relatie": t.contact, "referentie": t.document_reference, "rekening_bron": a["wachtrekening"]}
                    for t in sorted(txs, key=lambda x: (x.date or datetime.min, x.id or "")) if t.id not in weg]
        if a.get("map_id") is None:
            raise YukiError("Geef 'map_id' (archiefmap, zie yuki_archief_mappen).")
        g = next(x for x in GENERIC if x.tool == "yuki_archief_documenten_in_map")
        res = self._run_generic(g, {"administratie": a["administratie"], "domein": a.get("domein"), "map_id": a["map_id"], "van": a.get("van"), "tot": a.get("tot"),
                                    "max_paginas": 3, "vernieuwen": a.get("vernieuwen")})
        out = []
        for r in res.get("gegevens") or []:
            if not isinstance(r, dict):
                continue
            pick = lambda *ks: next((str(v) for k in ks for kk, v in r.items() if kk.lstrip("@").casefold() == k.casefold() and v not in (None, "", {})), None)
            did = pick("ID", "DocumentID")
            if not did:
                continue
            d = pick("DocumentDate", "Date", "Created", "Modified")
            out.append({"id": f"D:{did}", "bron": "documentworkflow", "datum": (d or "")[:10] or None, "omschrijving": pick("Subject", "Description", "Name"),
                        "bedrag": pick("Amount", "TotalAmount", "InvoiceAmount"), "relatie": pick("ContactName", "Contact", "FullName"),
                        "referentie": pick("Reference", "InvoiceNumber"), "btw_bedrag": pick("VATAmount")})
        out.sort(key=lambda x: (x["datum"] or "", x["id"]))
        return out

    def _boek_voorstel(self, a):
        if not boeking.write_enabled():
            return boeking.uit_tekst()
        h = self.handle(a)
        adm = h.administration
        klaar = boeking.behandeld(adm.id)
        items = [i for i in self._boek_items(h, a) if i["id"] not in klaar]
        if a.get("item_id"):
            item = next((i for i in self._boek_items(h, a) if i["id"] == a["item_id"]), None)
            if item is None:
                raise YukiError("Item niet gevonden in deze bron en periode.")
        else:
            if not items:
                return {"actief": True, "klaar": True, "uitleg": "Geen onbehandelde items meer in deze bron en periode.", "behandeld": len(klaar)}
            item = items[0]
        try:
            v = boeking.bouw_voorstel(item, a.get("aanpassingen") or {}, adm.id)
        except ValueError as e:
            raise YukiError(str(e))
        out: dict[str, Any] = {"actief": True, "administratie": adm.name, "item": item, "nog_te_behandelen": len(items), "voorstel": {k: v[k] for k in v if k != "journal_xml"}}
        if item["bron"] == "documentworkflow" and v["type"] in ("aankoop", "verkoop"):
            out["voorstel"].setdefault("waarschuwingen", []).append(
                "Dagboek: ProcessJournal boekt altijd een memoriaalpost (GeneralJournal), geen aankoop- of verkoopfactuur in het aankoop-/verkoopdagboek, "
                "en het workflowdocument krijgt hierdoor niet de backoffice-status 'Afgehandeld'. Voor Yuki is geen gedocumenteerde methode gevonden die een bestaand "
                "workflowdocument tot factuur verwerkt en afhandelt; afhandelen kan in de Yuki-interface (zie docs/BOEKINGSWORKFLOW.md).")
        if v["volledig"]:
            try:
                scheme = {x.code for x in h.gl_account_scheme()}
            except YukiError:
                scheme = set()
            onbekend = sorted({r["rekening"] for r in v["boekingsregels"]} - scheme) if scheme else []
            if onbekend:
                out["voorstel"]["rekening_onbekend"] = onbekend
                out["voorstel"]["volledig"] = False
                out["voorstel"]["ontbrekend"] = [f"rekening {c} bestaat niet in het rekeningschema van deze administratie" for c in onbekend]
                out["uitleg"] = "Corrigeer de rekening(en) met 'aanpassingen'; er is geen token uitgegeven."
                return out
            dc = dubbel.controleer(h, v["boekingsregels"], item, a.get("aanpassingen") or {})
            out["dubbelcontrole"] = dc
            basis = {"administratie": adm.name, "administratie_id": adm.id, "item": item["id"], "bron": item["bron"], "dubbelcontrole": dc["uitkomst"], "zekerheid": dc.get("zekerheid")}
            reden = (a.get("deblokkeer_reden") or "").strip()
            if dubbel.blokkeert(dc["uitkomst"]):
                if not (a.get("deblokkeren") is True and len(reden) >= dubbel.MIN_REDEN):
                    boeking.audit({**basis, "uitkomst": "geblokkeerd", "redenen": dc["redenen"]})
                    out["geblokkeerd"] = True
                    out["uitleg"] = (f"Item geblokkeerd: {dc['uitkomst']}. Er is geen token uitgegeven. Controleer in Yuki; wilt de gebruiker toch boeken, vraag dan "
                                     f"opnieuw met deblokkeren=true en deblokkeer_reden (minstens {dubbel.MIN_REDEN} tekens); dat komt in het auditlog.")
                    return out
                boeking.audit({**basis, "uitkomst": "gedeblokkeerd", "reden": reden[:300], "redenen": dc["redenen"]})
                out["gedeblokkeerd"] = {"reden": reden[:300]}
            if boeking.workflow_geblokkeerd(item["bron"], v["type"]):
                boeking.audit({**basis, "uitkomst": "workflow_geblokkeerd", "type": v["type"]})
                out["workflow_geblokkeerd"] = True
                out["geblokkeerd"] = True
                out["uitleg"] = boeking.WORKFLOW_BLOK + " Er is geen token uitgegeven. Gebruik dit voorstel (en de dubbelcontrole) als invoer voor het afhandelen in de backoffice."
                return out
            out["voorstel"]["journal_xml_dry_run"] = v["journal_xml"]
            out.update(boeking.nieuw_token(adm.id, adm.name, item["id"], item["bron"], v["journal_xml"], v["boekingsregels"], {"type": v["type"], **({"btw_nul": v.get("btw_nul")} if v.get("btw_nul") else {})}))
            out["uitleg"] = ("Toon dit voorstel aan de gebruiker. Boek pas na zijn uitdrukkelijke bevestiging met yuki_boeking_bevestigen "
                             "(token + voorstel_hash + bevestiging='ja'); één boeking per call. Wijzigt de gebruiker iets, vraag dan een nieuw voorstel.")
        else:
            out["uitleg"] = "Voorstel nog niet volledig: vul de ontbrekende velden aan via 'aanpassingen'. Er is geen token uitgegeven."
        return out

    def _boek_overslaan(self, a):
        if not boeking.write_enabled():
            return boeking.uit_tekst()
        h = self.handle(a)
        boeking.markeer(h.administration.id, str(a["item_id"]), "overgeslagen")
        boeking.audit({"administratie": h.administration.name, "administratie_id": h.administration.id, "item": a["item_id"], "uitkomst": "overgeslagen"})
        return {"overgeslagen": a["item_id"], "opmerking": "Alleen lokaal vastgelegd; niets in Yuki gewijzigd."}

    def _boek_bevestigen(self, a):
        if not boeking.write_enabled():
            raise YukiError("Schrijven staat uit. " + boeking.uit_tekst()["uitleg"])
        if a.get("bevestiging") != "ja" and not a.get("dry_run"):
            raise YukiError("Zonder uitdrukkelijke bevestiging (bevestiging='ja') wordt er niet geboekt.")
        c = self.f.get(a.get("domein"))
        adm = c.resolve(a["administratie"])
        t = boeking.controleer_token(a.get("token"), adm.id, a.get("voorstel_hash"))
        if boeking.workflow_geblokkeerd(t["bron"], (t.get("extra") or {}).get("type")):
            raise YukiError(boeking.WORKFLOW_BLOK)
        soap_xml = f'<xmlDoc>{t["xml"]}</xmlDoc>'
        if a.get("dry_run"):
            return {"dry_run": True, "geboekt": False, "administratie": adm.name, "methode": "Accounting.ProcessJournal",
                    "soap_body": f'<ProcessJournal xmlns="http://www.theyukicompany.com/"><sessionID>[GEHEIM]</sessionID><administrationID>{adm.id}</administrationID>{soap_xml}</ProcessJournal>',
                    "journal_xml": t["xml"], "boekingsregels": t["regels"], "token_blijft_geldig": True,
                    "opmerking": "Niets verstuurd. Dit is exact de XML die bij bevestiging naar Yuki gaat (niet live getest; zie docs/BOEKINGSWORKFLOW.md)."}
        if boeking.geboekt_vandaag() >= boeking.max_per_dag():
            raise YukiError(f"Dagmaximum aan boekingen bereikt ({boeking.max_per_dag()}); instelbaar met YUKI_WRITE_MAX_PER_DAY (maximum 100).")
        if boeking.workflow_geblokkeerd(t["bron"], (t.get("extra") or {}).get("type")):
            boeking.audit({"administratie": adm.name, "administratie_id": adm.id, "item": t["item_id"], "bron": t["bron"], "uitkomst": "workflow_geblokkeerd"})
            raise YukiError(boeking.WORKFLOW_BLOK)
        boeking.verbruik_token(a["token"])          # eenmalig: ook bij een fout is een nieuw voorstel nodig
        basis = {"administratie": adm.name, "administratie_id": adm.id, "item": t["item_id"], "bron": t["bron"], "voorstel_hash": t["hash"], "regels": t["regels"]}
        if (t.get("extra") or {}).get("btw_nul"):
            basis["btw_nul"] = t["extra"]["btw_nul"]
        boeking.audit({**basis, "uitkomst": "poging"})
        try:
            with c.sessions.transport.allow_journal_write():
                res = c.sessions.call("Accounting", "ProcessJournal", [("administrationID", adm.id), ("xmlDoc", RawXml(t["xml"]))],
                                      administration_id=adm.id, domain=adm.domain_id or a.get("domein") or None, force_refresh=True)
        except Exception as e:
            boeking.audit({**basis, "uitkomst": "fout", "fout": type(e).__name__ + ": " + str(e)[:200]})
            raise
        guid = (res.text or "").strip() if res is not None else ""
        boeking.markeer(adm.id, t["item_id"], "geboekt")
        boeking.audit({**basis, "uitkomst": "geboekt", "document_id": guid})
        return {"geboekt": True, "document_id": guid or None, "administratie": adm.name, "item": t["item_id"], "boekingsregels": t["regels"],
                "opmerking": "Eén journaalpost aangemaakt. Controleer ze in Yuki; deze boeking wordt niet automatisch gekoppeld aan het brondocument."}

    def _boek_status(self, a):
        tel = boeking.geboekt_vandaag() if boeking.write_enabled() else 0
        return {"actief": boeking.write_enabled(), "schakelaar": f"{boeking.ENV_ENABLE}=ja", "token_geldig_minuten": boeking.ttl_minuten(),
                "dagmaximum": boeking.max_per_dag(), "geboekt_vandaag": tel, "bulk": "onmogelijk: één token, één boeking",
                "methode": "Accounting.ProcessJournal (officieel gedocumenteerd; niet live getest)", "documentatie": "docs/BOEKINGSWORKFLOW.md"}

    # ----------------------------------------------------- kerntools
    def _status(self, a):
        q = self.f.quota()
        domains = [{"domain": s.domain, "calls_today": s.calls, "remaining": s.remaining, "limit": s.limit,
                    "warn_at": s.warn_at, "status": s.to_dict()["status"], "blocked": s.blocked} for s in q.all_today()]
        rc = ResponseCache()
        stats = rc.stats()
        return {"day": q.today(), "limit": q.limit, "standaard_limiet": 900, "gevraagde_limiet": self.f.limits.requested,
                "toegangsniveau": "portaal" if self.f.level == "portal" else "domein",
                "waarschuwingen": self.f.limits.warnings, "tekenaanname_crediteuren": creditor_sign(), "gratis": GRATIS_TEKST, "domains": domains,
                "cache": {d: v for d, v in stats.items()}, "editie": edition.EDITION}

    def _administraties(self, a):
        c = self.f.get(a.get("domein"))
        return [_jsonable(x) for x in c.list_administrations(with_internal_code=bool(a.get("met_interne_klantcode")), refresh=bool(a.get("vernieuwen")))]

    def _proefbalans(self, a):
        h = self.handle(a)
        soort = a.get("soort", "commercieel")
        return [_jsonable(x) for x in h.trial_balance(a["datum"], fiscaal=soort == "fiscaal", year_end=soort == "jaarafsluiting")]

    def _omzet(self, a):
        return _jsonable(self.handle(a).net_revenue(a["van"], a["tot"], fiscaal=bool(a.get("fiscaal"))))

    def _open(self, a):
        items = self._items(self.handle(a), a["soort"], a.get("peildatum"), normalize=False)
        return [{k: v for k, v in _jsonable(i).items()} for i in items]

    def _mutaties(self, a):
        return [_jsonable(x) for x in self.handle(a).gl_transactions(a["rekening"], a["van"], a["tot"], fiscaal=bool(a.get("fiscaal")))]

    def _schema(self, a):
        return [_jsonable(x) for x in self.handle(a).gl_account_scheme()]

    def _gewijzigd(self, a):
        return {"laatst_gewijzigd": _jsonable(self.handle(a).financial_year_modified(int(a["jaar_id"])))}

    def _jaartotalen(self, a):
        from yuki_core.tools import _analyze
        h = self.handle(a)
        j = int(a["boekjaar"])
        return _analyze(h, 1 if a.get("fiscaal") else 0, date(j, 1, 1), date(j, 12, 31), str(j), "saldo", None)

    # ----------------------------------------------------- analyses
    def _ouderdom(self, a):
        h = self.handle(a)
        peil = a.get("peildatum") or _today()
        items = self._items(h, a["soort"], a.get("peildatum"))
        kind = "Debtor" if a["soort"] == "debiteuren" else "Creditor"
        meth = f"Accounting.Outstanding{kind}Items" + ("ByDateOutstanding" if a.get("peildatum") else "")
        res = an.ouderdomsanalyse(items, peil, a.get("basis", "vervaldatum"))
        if res["negatieve_posten"]["aantal"]:
            res["afpuntingscheck_voorstel"] = _afp_voorstel(res["negatieve_posten"]["aantal"])
        return {**res, "bronnen": [meth],
                "aannames": ["Open bedrag > 0 = nog open; < 0 = negatief open bedrag: creditnota, betaling, voorschot of te veel betaald (na te gaan; live bevestigd in één dossier)."]}

    def _dso(self, a):
        h = self.handle(a)
        j = int(a["jaar"])
        van = date(j, 1, 1)
        tot = an._d(a["tot"]) if a.get("tot") else (min(_today(), date(j, 12, 31)) if j == _today().year else date(j, 12, 31))
        dagen = (tot - van).days + 1
        omzet = h.net_revenue(van, tot).amount
        deb = sum((an.D(i.open_amount) for i in self._items(h, "debiteuren", tot)), Decimal(0))
        end_lines = h.trial_balance(tot)
        inkopen = an.pl_periode(end_lines)["inkopen_60"]
        cred = sum((an.D(i.open_amount) for i in self._items(h, "crediteuren", tot)), Decimal(0))
        return {"periode": {"van": van.isoformat(), "tot": tot.isoformat()},
                "dso": an.dagen_ratio(deb, omzet, dagen, a.get("btw_percentage")),
                "dpo": an.dagen_ratio(cred, inkopen, dagen, a.get("btw_percentage")),
                "bronnen": ["Accounting.NetRevenue", "Accounting.GLAccountBalance", "Accounting.OutstandingDebtorItemsByDateOutstanding",
                            "Accounting.OutstandingCreditorItemsByDateOutstanding"],
                "aannames": ["Inkopen = klasse 60 (MAR) cumulatief sinds 1 januari; verifieer bij een afwijkend rekeningschema."]}

    def _top(self, a):
        h = self.handle(a)
        items = self._items(h, a["soort"], a.get("peildatum"))
        return {"soort": a["soort"], "top": an.top_relaties(items, int(a.get("aantal", 10))),
                "bronnen": ["Accounting.Outstanding" + ("Debtor" if a["soort"] == "debiteuren" else "Creditor") + "Items"]}

    def _vergelijk(self, a):
        h = self.handle(a)
        j, p = int(a["jaar"]), a["periode"]
        bron: list = []
        cur = self._pl(h, j, p, bron)
        out = {"periode": {"van": cur["van"].isoformat(), "tot": cur["tot"].isoformat()}, "huidig": {k: an.money(cur["pl"][k]) for k in ("omzet", "kosten", "resultaat")}}
        mode = a.get("vergelijk_met", "beide")
        if mode in ("vorige_periode", "beide"):
            pj, pp = an.vorige_periode(j, p)
            prev = self._pl(h, pj, pp, bron)
            out["vorige_periode"] = {"label": f"{pj} {pp}", **an.vergelijk(cur["pl"], prev["pl"])}
        if mode in ("vorig_jaar", "beide"):
            ly = self._pl(h, j - 1, p, bron)
            out["vorig_jaar"] = {"label": f"{j - 1} {p}", **an.vergelijk(cur["pl"], ly["pl"])}
        out["bronnen"] = bron
        out["aannames"] = ["Resultaatrekeningen zijn cumulatief binnen het boekjaar; geldt niet bij een gebroken boekjaar."]
        return out

    def _marge(self, a):
        h = self.handle(a)
        bron: list = []
        r = self._pl(h, int(a["jaar"]), a.get("periode", "jaar"), bron)
        return {**an.marge_kostenstructuur(r["pl"]), "bronnen": bron}

    def _liq(self, a):
        h = self.handle(a)
        lines = h.trial_balance(a["datum"])
        y = analysis.analyze_trial_balance(lines, administration_id=h.administration.id, tot=a["datum"]).to_dict()
        return {"ratio": an.liquiditeit_uit_ratios(y["ratios"]), "liquide_middelen": y["totals"]["liquide_middelen"],
                "bronnen": ["Accounting.GLAccountBalance"], "aannames": y["aannames"][:4]}

    def _uitschieters(self, a):
        h = self.handle(a)
        txs = h.gl_transactions(a["rekening"], a["van"], a["tot"])
        return {**an.uitschieters(txs, float(a.get("drempel", 3.5))), "bronnen": ["AccountingInfo.GetTransactionDetails"]}

    def _dashboard(self, a):
        h = self.handle(a)
        j = int(a["jaar"])
        per = a.get("periode", "jaar")
        bron: list = []
        r = self._pl(h, j, per, bron)
        lines = r["lines_end"]
        y = analysis.analyze_trial_balance(lines, administration_id=h.administration.id, tot=r["tot"]).to_dict()
        peil = a.get("peildatum") or min(_today(), r["tot"]).isoformat()
        deb = self._items(h, "debiteuren", None if not a.get("peildatum") else a["peildatum"])
        cred = self._items(h, "crediteuren", None if not a.get("peildatum") else a["peildatum"])
        bron += ["Accounting.OutstandingDebtorItems", "Accounting.OutstandingCreditorItems"]
        omzet_basis = r["pl"]["omzet"]
        dagen = (r["tot"] - r["van"]).days + 1
        data = {
            "administratie": h.administration.name,
            "periode": {"van": r["van"].isoformat(), "tot": r["tot"].isoformat(), "peildatum": peil},
            "kerncijfers": {"omzet": an.money(r["pl"]["omzet"]), "kosten": an.money(r["pl"]["kosten"]), "resultaat": an.money(r["pl"]["resultaat"]),
                            "liquide_middelen": y["totals"]["liquide_middelen"], "liquiditeit": y["ratios"]["liquiditeit"]["waarde"]},
            "debiteuren": {"ouderdom": an.ouderdomsanalyse(deb, peil), "top": an.top_relaties(deb, 5),
                           "dagen": an.dagen_ratio(sum((an.D(i.open_amount) for i in deb), Decimal(0)), omzet_basis, dagen)},
            "crediteuren": {"ouderdom": an.ouderdomsanalyse(cred, peil), "top": an.top_relaties(cred, 5),
                            "dagen": an.dagen_ratio(sum((an.D(i.open_amount) for i in cred), Decimal(0)), r["pl"]["inkopen_60"], dagen)},
            "btw": an.btw_saldo_indicatie(lines),
            "afpunting": {"debiteuren": self._afp_kort(deb, "debiteuren"), "crediteuren": self._afp_kort(cred, "crediteuren")},
            "bronnen": bron,
            "aannames": ["Resultaatrekeningen cumulatief binnen het boekjaar.", "Open bedrag > 0 = nog open, < 0 = negatief open bedrag: creditnota, betaling, voorschot of te veel betaald (na te gaan; live bevestigd in één dossier).",
                         "Btw-saldo is een indicatie op rekeningen 411/451, geen aangifte."],
        }
        n_neg = data["debiteuren"]["ouderdom"]["negatieve_posten"]["aantal"] + data["crediteuren"]["ouderdom"]["negatieve_posten"]["aantal"]
        if n_neg:
            data["afpuntingscheck_voorstel"] = _afp_voorstel(n_neg)
        safe = "".join(ch if ch.isalnum() else "-" for ch in h.administration.name).strip("-")[:40] or "dossier"
        fname = f"dashboard-{safe}-{j}.html"
        html = dashboard_html(data) if (a.get("export_map") or a.get("opslaan")) else ""
        if a.get("export_map"):
            d = Path(a["export_map"]).expanduser()
            d.mkdir(parents=True, exist_ok=True)
            p = d / fname
            p.write_text(html, encoding="utf-8")
            data["export_pad"] = str(p)
        data["opslag"] = opslag.bewaar(h.administration.name, {fname: html} if html else {}, bool(a.get("opslaan")), "dashboards")
        return data

    def _export_dataset(self, a):
        ds = a["dataset"]
        if ds not in exp.SCHEMAS:
            raise YukiError(f"Onbekende dataset '{ds}'. Kies: {', '.join(exp.SCHEMAS)}.")
        fm = list(a.get("formaten") or ["csv", "json"])
        bad = [f for f in fm if f not in exp.FORMATS]
        if bad:
            raise YukiError(f"Onbekend formaat {bad}. Kies uit: {', '.join(exp.FORMATS)}.")
        h = self.handle(a)
        naam = h.administration.name
        bron: list = []
        rows: list[dict] = []
        if ds == "kpis":
            j = int(a.get("jaar") or date.today().year)
            k = self._kpi_set(h, j, a.get("periode", "jaar"), a.get("peildatum"), False, bron)
            p = k["periode"]
            base = {"administratie": naam, "periode_van": p["van"], "periode_tot": p["tot"], "peildatum": p["peildatum"]}

            def put(kpi, waarde, eenheid="EUR"):
                if waarde is not None:
                    rows.append({**base, "kpi": kpi, "waarde": waarde, "eenheid": eenheid})
            for kk in ("omzet", "kosten", "resultaat", "liquide_middelen"):
                put(kk, k[kk])
            for soort in ("open_debiteuren", "open_crediteuren"):
                put(soort + "_totaal", k[soort]["totaal"])
                put(soort + "_vervallen", k[soort]["vervallen"])
                put(soort + "_negatieve_posten", k[soort]["negatieve_posten_na_te_gaan"], "aantal")
            mk = an.marge_kostenstructuur(self._pl(h, j, a.get("periode", "jaar"), bron)["pl"])
            put("brutomarge", mk["brutomarge_pct"], "procent")
            put("nettomarge", mk["nettomarge_pct"], "procent")
        elif ds == "saldi":
            j = int(a.get("jaar") or date.today().year)
            _, e = an.periode_bereik(j, a.get("periode", "jaar"))
            peil = a.get("peildatum") or e.isoformat()
            bron.append(f"Accounting.GLAccountBalance(transactionDate={peil})")
            for x in h.trial_balance(peil):
                d = _jsonable(x)
                rows.append({"administratie": naam, "peildatum": peil, "rekening_code": d.get("code"), "rekening_naam": d.get("name"), "saldo": d.get("balance")})
        else:
            soort = a.get("soort") or "debiteuren"
            if soort not in ("debiteuren", "crediteuren"):
                raise YukiError("soort moet debiteuren of crediteuren zijn.")
            peil = a.get("peildatum") or _today().isoformat()
            items = self._items(h, soort, a.get("peildatum"), normalize=False)
            bron.append("Accounting.Outstanding" + ("Debtor" if soort == "debiteuren" else "Creditor") + "Items")
            for i in items:
                d = _jsonable(i)
                due = (d.get("due_date") or "")[:10] or None
                b = an.bucket_for((date.fromisoformat(peil) - date.fromisoformat(due)).days) if due else "zonder_datum"
                if d.get("open_amount") is not None and d["open_amount"] < 0:
                    b = "negatief"
                rows.append({"administratie": naam, "soort": soort, "peildatum": peil, "relatie": d.get("contact"), "referentie": d.get("reference"),
                             "omschrijving": d.get("description"), "factuurdatum": (d.get("date") or "")[:10] or None, "vervaldatum": due,
                             "origineel_bedrag": d.get("original_amount"), "open_bedrag": d.get("open_amount"), "ouderdom_bucket": b})
        out: dict[str, Any] = {"dataset": ds, "administratie": naam, "aantal_rijen": len(rows), "schema": exp.schema_doc(ds), "voorbeeldrij": rows[0] if rows else None,
                               "bronnen": bron}
        if a.get("export_map"):
            out["bestanden"] = exp.write_all(Path(a["export_map"]).expanduser(), ds, rows, fm, {"administratie": naam, "bronnen": bron, "bron": ATTRIBUTION})
        else:
            out["opmerking"] = "Geen export_map opgegeven: er is niets weggeschreven."
        out["aannames"] = ["Open bedrag < 0 = negatief open bedrag (na te gaan); bucket 'negatief'.", "Geen fiscaal advies. Deel geen klantgegevens met derden."]
        return out

    def _kpi_set(self, h, jaar: int, periode: str, peildatum: Optional[str], vergelijk: bool, bron: list, compact: bool = False) -> dict:
        r = self._pl(h, jaar, periode, bron)
        lines = r["lines_end"]
        y = analysis.analyze_trial_balance(lines, administration_id=h.administration.id, tot=r["tot"]).to_dict()
        peil = peildatum or min(_today(), r["tot"]).isoformat()
        deb = self._items(h, "debiteuren", peildatum)
        cred = self._items(h, "crediteuren", peildatum)
        bron += ["Accounting.OutstandingDebtorItems", "Accounting.OutstandingCreditorItems"]
        od, oc = an.ouderdomsanalyse(deb, peil), an.ouderdomsanalyse(cred, peil)
        out: dict[str, Any] = {
            "periode": {"van": r["van"].isoformat(), "tot": r["tot"].isoformat(), "peildatum": peil},
            "omzet": an.money(r["pl"]["omzet"]), "kosten": an.money(r["pl"]["kosten"]), "resultaat": an.money(r["pl"]["resultaat"]),
            "liquide_middelen": y["totals"]["liquide_middelen"],
            "open_debiteuren": {"totaal": od["totaal_positief"], "vervallen": od["vervallen_totaal"], "negatieve_posten_na_te_gaan": od["negatieve_posten"]["aantal"]},
            "open_crediteuren": {"totaal": oc["totaal_positief"], "vervallen": oc["vervallen_totaal"], "negatieve_posten_na_te_gaan": oc["negatieve_posten"]["aantal"]},
        }
        if compact:
            return out
        mk = an.marge_kostenstructuur(r["pl"])
        dagen = (r["tot"] - r["van"]).days + 1
        out["marge"] = {"brutomarge_pct": mk["brutomarge_pct"], "nettomarge_pct": mk["nettomarge_pct"]}
        out["liquiditeit"] = an.liquiditeit_uit_ratios(y["ratios"])
        out["dso"] = an.dagen_ratio(sum((an.D(i.open_amount) for i in deb), Decimal(0)), r["pl"]["omzet"], dagen)
        out["dpo"] = an.dagen_ratio(sum((an.D(i.open_amount) for i in cred), Decimal(0)), r["pl"]["inkopen_60"], dagen)
        out["btw_indicatie"] = an.btw_saldo_indicatie(lines)
        if vergelijk:
            vj, vp = an.vorige_periode(jaar, periode)
            r2 = self._pl(h, vj, vp, bron)
            out["vergelijking_vorige_periode"] = {"periode": f"{vj} {vp}", **an.vergelijk(r["pl"], r2["pl"], ("huidig", "vorige"))}
        return out

    def _dossier_transfer(self, a):
        from . import transfer
        years = [int(y) for y in (a.get("jaren") or [])]
        if a.get("alle_jaren"):
            cur = date.today().year
            years = list(range(int(a.get("eerste_jaar") or cur - 5), cur + 1))
        if not years:
            raise YukiError("Geef 'jaren' (bv. [2025]) of 'alle_jaren'. De Yuki-API levert geen lijst van boekjaren.")
        try:
            return transfer.run_export(lambda n, x: self.call(n, x), administratie=a["administratie"], years=years, out=Path(a["export_map"]).expanduser(), domein=a.get("domein"),
                                       zip_years=bool(a.get("zip")), include_documents=bool(a.get("inclusief_documenten")), all_accounts=bool(a.get("alle_rekeningen")),
                                       start_month=int(a.get("start_maand_boekjaar") or 1), formats=a.get("formaten") or None, resume=a.get("hervat", True) is not False,
                                       threshold=int(a.get("drempel") or transfer.THRESHOLD), confirmed=bool(a.get("bevestig")), estimate_only=bool(a.get("alleen_schatting")),
                                       debtor_prefix=a.get("debiteurenprefix") or "40", creditor_prefix=a.get("crediteurenprefix") or "44")
        except transfer.TransferError as exc:
            raise YukiError(str(exc))

    def _dashboard_kpis(self, a):
        h = self.handle(a)
        bron: list = []
        data = self._kpi_set(h, int(a["jaar"]), a.get("periode", "jaar"), a.get("peildatum"), bool(a.get("vergelijk_vorige_periode")), bron)
        return {"administratie": h.administration.name, **data, "bronnen": bron,
                "aannames": ["Resultaatrekeningen cumulatief binnen het boekjaar (Belgisch MAR).",
                             "Open bedrag < 0 = negatief open bedrag (creditnota, betaling, voorschot of te veel betaald: na te gaan).",
                             "Btw-saldo is een indicatie op rekeningen 411/451, geen aangifte.", "Geen fiscaal advies: laat cijfers nakijken door uw boekhouder."]}

    def _portfolio_kpis(self, a):
        mx = max(1, min(int(a.get("max_administraties") or 5), 15))
        namen = list(a.get("administraties") or [])
        if not namen:
            c0 = self.f.get(a.get("domein"))
            namen = [x.name if getattr(x, "name", None) else str(x) for x in c0.list_administrations(refresh=bool(a.get("vernieuwen")))][:mx]
        if len(namen) > mx:
            raise YukiError(f"Te veel administraties ({len(namen)}); maximum {mx}. Splits de opdracht of verhoog max_administraties (max 15).")
        rijen, bron, fouten = [], [], 0
        for naam in namen:
            try:
                h = self.handle({"administratie": naam, "domein": a.get("domein"), "vernieuwen": a.get("vernieuwen")})
                k = self._kpi_set(h, int(a["jaar"]), a.get("periode", "jaar"), a.get("peildatum"), False, bron, compact=True)
                rijen.append({"administratie": h.administration.name, **k})
            except YukiDailyLimitReached:
                raise
            except Exception as exc:  # noqa: BLE001 - één dossier mag de rest niet stoppen
                fouten += 1
                rijen.append({"administratie": str(naam), "fout": scrub(str(exc))[:300]})
        ok = [r for r in rijen if "fout" not in r]
        tot = {k: round(sum(r[k] for r in ok), 2) for k in ("omzet", "kosten", "resultaat", "liquide_middelen")}
        tot["open_debiteuren"] = round(sum(r["open_debiteuren"]["totaal"] for r in ok), 2)
        tot["open_crediteuren"] = round(sum(r["open_crediteuren"]["totaal"] for r in ok), 2)
        return {"jaar": int(a["jaar"]), "periode": a.get("periode", "jaar"), "aantal_administraties": len(rijen), "aantal_fouten": fouten,
                "administraties": rijen, "totaal": tot, "bronnen": sorted(set(bron)),
                "aannames": ["Per administratie opgehaald; bedragen in de valuta van de administratie, het totaal telt ze zonder omrekening op.",
                             "Kost ongeveer 4 Yuki-calls per administratie; controleer yuki_status bij grote portefeuilles.",
                             "Geen fiscaal advies. Deel geen klantgegevens met derden."]}

    def _afp_kort(self, items, soort: str) -> dict:
        r = afp.afpuntingsvoorstellen(items, soort)
        top = [{k: v[k] for k in ("id", "type", "zekerheid", "zekerheid_label", "relaties", "som_betalingen", "som_facturen", "verschil")}
               for v in r["voorstellen"][:5]]
        return {"samenvatting": r["samenvatting"], "top_voorstellen": top,
                "suggestie": "Open yuki_afpuntingsvoorstellen voor alle voorstellen in detail." if r["voorstellen"] else None}

    def _afpunting(self, a):
        h = self.handle(a)
        soorten = ["debiteuren", "crediteuren"] if a.get("soort", "beide") == "beide" else [a["soort"]]
        out: dict[str, Any] = {"administratie": h.administration.name, "peildatum": a.get("peildatum") or _today().isoformat(), "bronnen": [], "resultaten": {}}
        for sd in soorten:
            items = self._items(h, sd, a.get("peildatum"))
            r = afp.afpuntingsvoorstellen(items, sd, a.get("tolerantie", 0.05), int(a.get("max_posten", 6)), int(a.get("max_combinaties", 20000)),
                                          a.get("relatieoverschrijdend", True), bool(a.get("ook_enkel_bedrag")), float(a.get("minimum_zekerheid", 0)))
            out["resultaten"][sd] = afp.zonder_intern(r)
            out["bronnen"].append("Accounting.Outstanding" + ("Debtor" if sd == "debiteuren" else "Creditor") + "Items" + ("ByDateOutstanding" if a.get("peildatum") else ""))
        out["aannames"] = ["Open bedrag < 0 = meestal een betaling zonder (gekoppelde) factuur; > 0 = factuur nog open (na normalisatie van het crediteurenteken).",
                           "Enkel voorstellen; afpunten gebeurt door de gebruiker of boekhouder in Yuki."]
        safe = "".join(ch if ch.isalnum() else "-" for ch in h.administration.name).strip("-")[:40] or "dossier"
        stem = f"afpuntingsvoorstellen-{safe}-{out['peildatum']}"
        files: dict[str, str] = {}
        if a.get("export_map") or a.get("opslaan"):
            files = {stem + ".csv": afpunting_csv(out), stem + ".html": afpunting_html(out)}
        if a.get("export_map"):
            d = Path(a["export_map"]).expanduser()
            d.mkdir(parents=True, exist_ok=True)
            out["bestanden"] = []
            for fn, inh in files.items():
                (d / fn).write_text(inh, encoding="utf-8-sig" if fn.endswith(".csv") else "utf-8", newline="" if fn.endswith(".csv") else None)
                out["bestanden"].append(str(d / fn))
        out["opslag"] = opslag.bewaar(h.administration.name, files, bool(a.get("opslaan")), "afpunting")
        return out

    def _opslag_status(self, a):
        return opslag.status(a.get("administratie"))

    def _opslag_instellen(self, a):
        try:
            return opslag.instellen(a.get("administratie"), a.get("type"), a.get("pad"), a.get("sync_map"), a.get("doelpad"), bool(a.get("wissen")))
        except ValueError as e:
            raise YukiError(str(e))

    def _mail(self, a):
        h = self.handle(a)
        items = self._items(h, a["soort"], a.get("peildatum"))
        q = a["relatie"].casefold()
        names = sorted({i.contact for i in items if i.contact and q in i.contact.casefold()})
        if not names:
            raise YukiError("Geen relatie gevonden met die naam in de openstaande posten.")
        exact = [n for n in names if n.casefold() == q]
        if len(names) > 1 and not exact:
            raise YukiError("Meerdere relaties gevonden; verfijn de naam: " + "; ".join(names[:10]))
        naam = exact[0] if exact else names[0]
        sel = [i for i in items if i.contact == naam]
        res_afp = afp.afpuntingsvoorstellen(items, a["soort"])
        gedekt = afp.gedekte_sleutels(items, res_afp)
        r = bouw_concept(naam, sel, a.get("peildatum") or _today(), a["soort"], a.get("aanspreekvorm", "u"), a.get("aanhef"),
                         a.get("handtekening"), a.get("aan"), a.get("cc"), a.get("eml_map"), afgepunt_sleutels=gedekt)
        r["opslag"] = opslag.bewaar(h.administration.name, {f"herinneringsmail-{naam}.txt": r["tekst"], f"herinneringsmail-{naam}.html": r["html"]},
                                    bool(a.get("opslaan")), "mails")
        return r

    def _handleiding(self, a):
        md = handleiding_md()
        if edition.REQUIRE_ATTRIBUTION:
            md += "\n" + ATTRIBUTION + "\n"
        ensure(md, edition.REQUIRE_ATTRIBUTION)
        html = handleiding_html()
        out = {"markdown": md}
        if a.get("export_map"):
            d = Path(a["export_map"]).expanduser()
            d.mkdir(parents=True, exist_ok=True)
            (d / "handleiding-saldi.md").write_text(md, encoding="utf-8")
            (d / "handleiding-saldi.html").write_text(html, encoding="utf-8")
            out["bestanden"] = [str(d / "handleiding-saldi.md"), str(d / "handleiding-saldi.html")]
        if a.get("opslaan"):
            if not a.get("administratie"):
                raise YukiError("Geef 'administratie' mee om op te slaan: de opslaglocatie wordt per administratie bepaald.")
            out["opslag"] = opslag.bewaar(a["administratie"], {"handleiding-saldi.md": md, "handleiding-saldi.html": html}, True, "handleiding")
        return out

    # ----------------------------------------------------- generiek
    def _add_generic(self, g: G) -> None:
        props: dict[str, Any] = {}
        req: list[str] = []
        if g.scope in ("admin", "admin_opt"):
            props["administratie"] = ADM
            if g.scope == "admin":
                req.append("administratie")
        if g.scope in ("contact", "domain"):
            props["administratie"] = S("Optioneel: administratie waarvan het domein gebruikt wordt (nodig bij een accountantssleutel).")
            props["domein_id"] = S("Domein-ID (GUID). Bij een accountantssleutel is administratie of domein_id nodig; zie yuki_domeinen.")
        props["domein"] = DOM
        for p in g.params:
            t = {"s": "string", "d": "string", "i": "integer", "b": "boolean"}[p.kind]
            sch: dict[str, Any] = {"type": t, "description": (p.desc or p.name) + (" (JJJJ-MM-DD)" if p.kind == "d" else "")}
            if p.enum:
                sch["enum"] = p.enum
            props[p.name] = sch
            if p.req:
                req.append(p.name)
        if g.pag:
            props.update(PAG_PROPS)
        props["vernieuwen"] = VERN
        desc = (g.desc + " Alleen lezen; bronmethode(s): " + ", ".join(f"{g.service}.{m}" for m in all_methods(g)) +
                ". Niet live bevestigd tegen een echt dossier.")
        self.add(g.tool, g.title, desc, obj(props, req), lambda a, g=g: self._run_generic(g, a))

    def _ensure_domain(self, c, a: dict) -> Optional[str]:
        """Bepaal het domein-ID voor domeingebonden calls en zet het als huidig domein (alleen bij portaalsleutel)."""
        dom = a.get("domein_id")
        if not dom and a.get("administratie"):
            dom = c.resolve(a["administratie"]).domain_id
        if self.f.level == "portal":
            if not dom:
                raise YukiError("Accountantssleutel heeft geen huidig domein: geef administratie of domein_id mee (zie yuki_domeinen).")
            if self._current.get(id(c)) != dom:
                tr = c.sessions.transport
                with tr.allow_set_domain():
                    c.sessions.call("Accounting", "SetCurrentDomain", [("domainID", dom)], domain=dom, force_refresh=True)
                self._current[id(c)] = dom
            return dom
        if not dom:
            res = c.sessions.call("Accounting", "GetCurrentDomain", [], domain=a.get("domein") or None)
            dom = (res.text or "").strip() if res is not None else ""
        return dom or None

    def _run_generic(self, g: G, a: dict) -> dict:
        c = self.f.get(a.get("domein"))
        method = g.pick(a) if g.pick else g.method
        if not is_allowed(g.service, method):
            raise YukiError(f"{g.service}.{method} is geen toegelaten leesmethode")
        params: list = []
        admin_id = None
        domain = a.get("domein") or None
        if g.scope in ("admin", "admin_opt") and (g.scope == "admin" or a.get("administratie")):
            adm = c.resolve(a["administratie"])
            admin_id, domain = adm.id, (adm.domain_id or domain)
            params.append(("administrationID", adm.id))
        if g.scope in ("contact", "domain"):
            dom_id = self._ensure_domain(c, a)
            domain = dom_id or domain
            if g.scope == "contact":
                params.append(("domainID", dom_id or ""))
        for p in g.params:
            if not p.soap:
                continue
            v = a.get(p.name)
            if v is None:
                if p.req:
                    raise YukiError(f"Parameter '{p.name}' is verplicht")
                continue
            params.append((p.soap, _dt(v) if p.kind == "d" else int(v) if p.kind == "i" else bool(v) if p.kind == "b" else str(v)))
        refresh = bool(a.get("vernieuwen"))

        def one(extra: list):
            return c.sessions.call(g.service, method, order_params(method, params, extra), administration_id=admin_id, domain=domain, force_refresh=refresh)

        bron = [f"{g.service}.{method}"]
        if not g.pag:
            rows, raw = rows_of(one([]))
            return {"methode": bron[0], "aantal": len(rows), "gegevens": rows if rows else raw, "bronnen": bron}
        kind = g.pag[0]
        size = int(a.get("paginagrootte", 100))
        start = int(a.get("start", 0 if kind == "record" else 1))
        maxp = int(a.get("max_paginas", 20))
        alle = a.get("alle_paginas", True)
        rows_all: list = []
        seen: set = set()
        pages, volledig, reden, volgende = 0, True, None, None
        pos = start
        while True:
            extra = [(g.pag[1], size), (g.pag[2], pos)] if kind == "record" else [(g.pag[1], pos)]
            try:
                rows, _ = rows_of(one(extra))
            except YukiDailyLimitReached:
                volledig, reden, volgende = False, "daglimiet bereikt", pos
                break
            pages += 1
            new = 0
            for r in rows:
                k = json.dumps(r, sort_keys=True, default=str)
                if k not in seen:
                    seen.add(k)
                    rows_all.append(r)
                    new += 1
            if not rows or new == 0 or (kind == "record" and len(rows) < size):
                break
            pos += size if kind == "record" else 1
            if not alle:
                volledig, reden, volgende = False, "alle_paginas=false", pos
                break
            if pages >= maxp:
                volledig, reden, volgende = False, "max_paginas bereikt", pos
                break
            if len(rows_all) >= MAX_ROWS:
                volledig, reden, volgende = False, f"{MAX_ROWS} rijen bereikt", pos
                break
        return {"methode": bron[0], "aantal": len(rows_all), "gegevens": rows_all, "paginas": pages, "volledig": volledig,
                "reden_onvolledig": reden, "volgende_start": volgende, "bronnen": bron}
