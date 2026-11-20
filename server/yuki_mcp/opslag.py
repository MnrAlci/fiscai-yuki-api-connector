"""Opslaglocatie van het permanente dossier: de gebruiker kiest, de plugin legt niets op.

- Keuze wordt lokaal bewaard (opslag.json in de datamap, 0600), per administratie of (op uitdrukkelijk verzoek) voor alle.
- Zonder keuze wordt gevraagd; er is geen standaardlocatie.
- Zelf schrijven doet de plugin alleen naar een lokale map. Voor cloud geeft ze een opslagvoorstel + instructie voor de
  gekozen connector; er wordt nooit iets geüpload.
- Lokaal wegschrijven van exports is geen Yuki-schrijfactie: Yuki blijft alleen-lezen.
"""
from __future__ import annotations

import json
import os
import re
import tempfile
from datetime import date
from pathlib import Path
from typing import Any, Optional

from yuki_core.paths import default_data_dir, secure_dir

from . import edition

try:                                   # alleen aanwezig in editie A
    from . import intern_rules
except ImportError:                    # editie B
    intern_rules = None

TYPES = {
    "lokaal": {
        "naam": "Lokale map op deze computer",
        "koppeling": "Geen extra koppeling nodig: de plugin schrijft zelf naar de gekozen map.",
        "installatie": ["Kies een bestaande of nieuwe map (absoluut pad). De plugin maakt submappen per administratie aan."],
        "betalend": False,
    },
    "onedrive": {
        "naam": "Microsoft OneDrive",
        "koppeling": "Een OneDrive-connector (MCP) of de lokale OneDrive-synchronisatiemap.",
        "installatie": ["Optie 1: registreer een OneDrive/Microsoft 365-connector (MCP) in uw assistent en meld u aan met uw Microsoft-account.",
                        "Optie 2: gebruik de gesynchroniseerde OneDrive-map op uw computer en geef die als 'sync_map' op; "
                        "de plugin schrijft dan lokaal en de OneDrive-app synchroniseert."],
        "betalend": "kan betalend zijn (Microsoft 365-abonnement of extra opslag)",
    },
    "sharepoint": {
        "naam": "Microsoft SharePoint",
        "koppeling": "Een SharePoint-connector (MCP) of een lokaal gesynchroniseerde documentbibliotheek.",
        "installatie": ["Optie 1: registreer een SharePoint/Microsoft 365-connector (MCP) en meld u aan met een account dat toegang heeft tot de site.",
                        "Optie 2: synchroniseer de documentbibliotheek met de OneDrive-app en geef de lokale map op als 'sync_map'."],
        "betalend": "kan betalend zijn (Microsoft 365-licentie vereist)",
    },
    "google_drive": {
        "naam": "Google Drive",
        "koppeling": "Een Google Drive-connector (MCP) of de lokale Drive-synchronisatiemap.",
        "installatie": ["Optie 1: registreer een Google Drive-connector (MCP) en geef toegang met uw Google-account.",
                        "Optie 2: gebruik 'Google Drive voor desktop' en geef de lokale map op als 'sync_map'."],
        "betalend": "gratis tot een opslaglimiet; zakelijk gebruik (Google Workspace) en extra opslag zijn betalend",
    },
    "dropbox": {
        "naam": "Dropbox",
        "koppeling": "Een Dropbox-connector (MCP) of de lokale Dropbox-map.",
        "installatie": ["Optie 1: registreer een Dropbox-connector (MCP) en geef toegang met uw Dropbox-account.",
                        "Optie 2: gebruik de Dropbox-app en geef de lokale Dropbox-map op als 'sync_map'."],
        "betalend": "gratis met beperkte opslag; meer ruimte en teamfuncties zijn betalend",
    },
    "dossierbeheer": {
        "naam": "Dossierbeheerpakket (DMS)",
        "koppeling": "De connector of API van uw dossierbeheerpakket, of een door dat pakket bewaakte map.",
        "installatie": ["Vraag bij uw leverancier of er een MCP-connector of API bestaat; zo niet, bewaar de export in de map die het pakket inleest "
                        "en geef die op als 'sync_map'."],
        "betalend": "dossierbeheerpakketten zijn meestal betalend; check de voorwaarden van uw leverancier",
    },
    "geen": {
        "naam": "Niets bewaren",
        "koppeling": "Geen: exports blijven in het antwoord en worden nergens bewaard.",
        "installatie": [],
        "betalend": False,
    },
}
CLOUD = {"onedrive", "sharepoint", "google_drive", "dropbox", "dossierbeheer"}
ALLE = "*"


def config_pad() -> Path:
    return secure_dir(default_data_dir()) / "opslag.json"


def _lees() -> dict:
    p = config_pad()
    if not p.exists():
        return {"versie": 1, "locaties": {}}
    try:
        d = json.loads(p.read_text(encoding="utf-8"))
        return d if isinstance(d, dict) and isinstance(d.get("locaties"), dict) else {"versie": 1, "locaties": {}}
    except (OSError, ValueError):
        return {"versie": 1, "locaties": {}}


def _schrijf(d: dict) -> None:
    p = config_pad()
    fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".tmp-", suffix=".json")
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        json.dump(d, fh, ensure_ascii=False, indent=1)
    os.chmod(tmp, 0o600)
    os.replace(tmp, p)


def _sleutel(administratie: Optional[str]) -> str:
    a = (administratie or "").strip()
    return ALLE if a in ("", ALLE) else a.casefold()


def opties() -> list[dict]:
    return [{"type": k, "naam": v["naam"], "betalend": v["betalend"]} for k, v in TYPES.items()]


def vraag() -> dict:
    voorbeeld = (intern_rules.OPSLAG_VOORBEELD if (edition.INTERNAL_RULES and intern_rules) else None)
    out = {"keuze_nodig": True,
           "vraag": "Waar wilt u het permanente dossier van deze cliënt bewaren? U beslist; de plugin legt geen standaardlocatie op.",
           "opties": opties(),
           "volgende_stap": "Antwoord met yuki_opslag_instellen (type, en voor 'lokaal' het mappad)."}
    if voorbeeld:
        out["voorbeeld"] = voorbeeld
    return out


def koppeling_uitleg(type_: str) -> dict:
    t = TYPES[type_]
    out = {"gekozen": type_, "naam": t["naam"], "benodigde_koppeling": t["koppeling"], "installatie": t["installatie"],
           "kan_betalend_zijn": t["betalend"] or "nee (de plugin zelf is gratis)",
           "neutraal": "Dit is geen aanbeveling van een product of dienst; kies wat bij uw kantoor past."}
    if edition.INTERNAL_RULES and intern_rules and type_ in ("sharepoint", "onedrive"):
        out["voorbeeld"] = intern_rules.OPSLAG_VOORBEELD
    return out


def status(administratie: Optional[str] = None) -> dict:
    cfg = _lees()["locaties"]
    if administratie:
        k = _sleutel(administratie)
        loc = cfg.get(k) or cfg.get(ALLE)
        if not loc:
            return vraag() | {"administratie": administratie}
        return {"keuze_nodig": False, "administratie": administratie, "locatie": loc,
                "geldt_voor": "deze administratie" if k in cfg else "alle administraties (op uw uitdrukkelijk verzoek)",
                **koppeling_uitleg(loc["type"]), "config_bestand": str(config_pad())}
    if not cfg:
        return vraag()
    return {"keuze_nodig": False, "locaties": cfg, "opties": opties(), "config_bestand": str(config_pad())}


def instellen(administratie: Optional[str], type_: Optional[str], pad: Optional[str] = None, sync_map: Optional[str] = None,
              doelpad: Optional[str] = None, wissen: bool = False) -> dict:
    k = _sleutel(administratie)
    d = _lees()
    if wissen:
        d["locaties"].pop(k, None)
        _schrijf(d)
        return {"gewist": True, "voor": "alle administraties" if k == ALLE else administratie, **status(administratie if k != ALLE else None)}
    if not type_:
        return vraag() | {"administratie": administratie}
    if type_ not in TYPES:
        raise ValueError("Onbekend type. Kies uit: " + ", ".join(TYPES))
    loc: dict[str, Any] = {"type": type_, "ingesteld_op": date.today().isoformat()}
    if type_ == "lokaal":
        if not pad:
            raise ValueError("Voor 'lokaal' is 'pad' (absolute map) verplicht.")
        p = Path(pad).expanduser()
        if not p.is_absolute():
            raise ValueError("'pad' moet een absoluut pad zijn.")
        loc["pad"] = str(p)
    if type_ in CLOUD:
        if sync_map:
            p = Path(sync_map).expanduser()
            if not p.is_absolute():
                raise ValueError("'sync_map' moet een absoluut pad zijn.")
            loc["sync_map"] = str(p)
        if doelpad:
            loc["doelpad"] = str(doelpad)[:300]
    d["locaties"][k] = loc
    _schrijf(d)
    return {"opgeslagen": True, "voor": "alle administraties" if k == ALLE else administratie, "locatie": loc,
            **koppeling_uitleg(type_),
            "opmerking": "Alleen uw lokale configuratie is aangepast; er is niets in Yuki gewijzigd en niets geüpload."}


def _veilig(naam: str, maxlen: int = 60) -> str:
    return re.sub(r"[^A-Za-z0-9._-]+", "-", naam).strip("-.")[:maxlen] or "dossier"


def bewaar(administratie: str, bestanden: dict[str, str], opslaan: bool, submap: str = "") -> dict:
    """Optioneel opslaan. Schrijft nooit zonder opslaan=True in deze call; cloud: enkel voorstel (of schrijven naar sync_map)."""
    st = status(administratie)
    if not opslaan:
        if st.get("keuze_nodig"):
            return {"opgeslagen": False, "info": "Nog geen opslaglocatie gekozen. Vraag de gebruiker en gebruik yuki_opslag_instellen; "
                                                 "geef daarna opslaan=true om te bewaren."}
        return {"opgeslagen": False, "gekozen_locatie": st["locatie"]["type"],
                "info": "Niet opgeslagen. Geef opslaan=true in deze call om naar de gekozen locatie te bewaren."}
    if st.get("keuze_nodig"):
        return {"opgeslagen": False, **st, "info": "Geen opslaglocatie gekozen: er is niets bewaard."}
    loc = st["locatie"]
    t = loc["type"]
    if t == "geen":
        return {"opgeslagen": False, "gekozen_locatie": "geen", "info": "U koos 'niets bewaren': er is niets opgeslagen."}
    naam = _veilig(administratie)
    sub = _veilig(submap) if submap else ""
    schrijfmap: Optional[Path] = None
    if t == "lokaal":
        schrijfmap = Path(loc["pad"]) / naam
    elif t in CLOUD and loc.get("sync_map"):
        schrijfmap = Path(loc["sync_map"]) / naam
    if schrijfmap is not None:
        if sub:
            schrijfmap = schrijfmap / sub
        schrijfmap.mkdir(parents=True, exist_ok=True)
        pads = []
        for fn, inhoud in bestanden.items():
            f = schrijfmap / _veilig(fn, 120)
            f.write_text(inhoud, encoding="utf-8")
            pads.append(str(f))
        out = {"opgeslagen": True, "gekozen_locatie": t, "bestanden": pads,
               "opmerking": "Lokaal weggeschreven; dit is geen Yuki-schrijfactie."}
        if t in CLOUD:
            out["opmerking"] += " De synchronisatie naar " + TYPES[t]["naam"] + " gebeurt door uw eigen synchronisatie-app."
        return out
    doel = (loc.get("doelpad") or f"<kies de map van de administratie>/{naam}") + (f"/{sub}" if sub else "")
    return {"opgeslagen": False, "gekozen_locatie": t, "voorstel": {"doelpad": doel, "bestandsnamen": [_veilig(f, 120) for f in bestanden]},
            "instructie": f"Upload niet automatisch. Maak deze bestanden zelf aan via uw {TYPES[t]['naam']}-connector in het doelpad "
                          f"(de inhoud staat in dit resultaat of in een lokale export_map). Benodigde koppeling: {TYPES[t]['koppeling']}",
            "installatie": TYPES[t]["installatie"], "kan_betalend_zijn": TYPES[t]["betalend"] or "nee"}
