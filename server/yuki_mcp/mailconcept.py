"""Conceptmail voor openstaande posten. Bouwt alleen tekst/HTML/.eml; verstuurt nooit iets.

Bewust geen netwerk-, SMTP- of procescode in deze module (afgedwongen door een test).
"""
from __future__ import annotations

import os
from datetime import date, datetime
from decimal import Decimal
from email.message import EmailMessage
from email.utils import format_datetime
from html import escape
from pathlib import Path
from typing import Any, Iterable, Optional

from . import edition
from .analytics import D, _d, _get
from .attribution import ATTRIBUTION, ensure
from .handleiding import handleiding_tekst_kort

try:                                   # alleen aanwezig in editie A
    from . import intern_rules
except ImportError:                    # editie B
    intern_rules = None

MAIL_STIJL_B = "font-family:Calibri,Arial,sans-serif;font-size:11pt;color:#222222"


def eur(x: Decimal | float) -> str:
    """Belgische notatie: 1.234,56."""
    v = D(x).quantize(Decimal("0.01"))
    s = f"{abs(v):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return ("-" if v < 0 else "") + "€ " + s


def _datum(x: Any) -> str:
    d = _d(x)
    return d.strftime("%d/%m/%Y") if d else "-"


def _neg_tekst(soort: str, n: int, bedrag: Decimal, je_u) -> str:
    woord = "post" if n == 1 else "posten"
    kern = f"Daarnaast {'staat' if n == 1 else 'staan'} er {n} negatieve {woord} van samen {eur(bedrag)} open. Dit is geen schuld: het verlaagt het totaal. "
    if soort == "debiteuren":
        return (kern + f"Meestal is het een betaling van {je_u('u', 'jou')} waar bij ons nog geen (gekoppelde) factuur tegenover staat; minder vaak een "
                "creditnota of een voorschot. Wij laten dit nakijken en koppelen het aan de juiste factuur.")
    return (kern + "Meestal is het een betaling aan " + je_u("u", "jou") + " waarvoor wij nog geen (gekoppelde) factuur hebben; minder vaak een creditnota of "
            f"een voorschot. Kunt {je_u('u', 'je')} ons de bijhorende factuur bezorgen?")


def _default_signature() -> str:
    if edition.INTERNAL_RULES and intern_rules:
        return intern_rules.DEFAULT_SIGNATURE
    return os.environ.get("YUKI_MAIL_SIGNATURE", "").strip() or "[Handtekening]"


def bouw_concept(relatie: str, items: Iterable[Any], peildatum: date | datetime | str, soort: str = "debiteuren",
                 aanspreekvorm: str = "u", aanhef: Optional[str] = None, handtekening: Optional[str] = None,
                 aan: Optional[str] = None, cc: Optional[str] = None, eml_map: Optional[str | Path] = None,
                 handleiding_in_mail: bool = True, afgepunt_sleutels: Optional[set] = None) -> dict:
    if soort not in ("debiteuren", "crediteuren"):
        raise ValueError("soort moet 'debiteuren' of 'crediteuren' zijn")
    if aanspreekvorm not in ("u", "je"):
        raise ValueError("aanspreekvorm moet 'u' of 'je' zijn")
    items = list(items)
    from .afpunting import item_key
    gedekt = afgepunt_sleutels or set()
    open_posten = [i for i in items if D(_get(i, "open_amount")) > 0 and item_key(i) not in gedekt]
    mogelijk_betaald = [i for i in items if D(_get(i, "open_amount")) > 0 and item_key(i) in gedekt]
    negatieven = [i for i in items if D(_get(i, "open_amount")) < 0 and item_key(i) not in gedekt]
    if not open_posten and not negatieven and not mogelijk_betaald:
        raise ValueError("Geen openstaande posten voor deze relatie: geen mail nodig.")
    totaal = sum((D(_get(i, "open_amount")) for i in open_posten), Decimal(0))
    neg_totaal = sum((D(_get(i, "open_amount")) for i in negatieven), Decimal(0))
    pd = _datum(peildatum)
    u = aanspreekvorm == "u"
    je_u = (lambda a, b: a if u else b)
    if aanhef is None:
        aanhef = intern_rules.DEFAULT_AANHEF if (edition.INTERNAL_RULES and intern_rules) else f"Beste {relatie},"
    sig = handtekening if handtekening is not None else _default_signature()

    if not open_posten:
        onderwerp = f"Afstemming openstaande posten per {pd}"
        intro = (f"Bij onze afstemming per {pd} vonden wij geen facturen die zeker nog open staan, wel enkele posten die wij nog laten nakijken.")
        vragen = [f"Klopt dit volgens {je_u('u', 'jou')}? Laat het ons dan weten."]
    elif soort == "debiteuren":
        onderwerp = f"Openstaande facturen per {pd}"
        intro = (f"Volgens onze boekhouding staan er per {pd} nog {len(open_posten)} "
                 f"factu{'ur' if len(open_posten) == 1 else 'ren'} open. Hieronder vindt {je_u('u', 'je')} het overzicht.")
        vragen = [f"Hebt {je_u('u', 'je')} al betaald? Laat ons dan de betaaldatum weten.",
                  f"Klopt een bedrag of factuur niet volgens {je_u('u', 'jou')}? Laat het ons dan weten.",
                  f"Kunt {je_u('u', 'je')} de openstaande bedragen binnen de week betalen? Alvast bedankt."]
    else:
        onderwerp = f"Afstemming openstaande facturen per {pd}"
        intro = (f"Bij onze afstemming staan er per {pd} nog {len(open_posten)} "
                 f"factu{'ur' if len(open_posten) == 1 else 'ren'} van {je_u('u', 'jou')} open in onze boekhouding. "
                 f"Hieronder vindt {je_u('u', 'je')} het overzicht.")
        vragen = [f"Klopt dit overzicht volgens {je_u('u', 'jou')}?",
                  f"Ontbreekt er een factuur of creditnota? Bezorg ons die dan graag."]
    regels_tekst = [f"{_get(i, 'reference') or '-'} | factuurdatum {_datum(_get(i, 'date'))} | "
                    f"vervaldatum {_datum(_get(i, 'due_date'))} | openstaand {eur(D(_get(i, 'open_amount')))}"
                    for i in open_posten]
    tekst = [aanhef, "", intro, ""] + regels_tekst + ["", f"Totaal openstaand: {eur(totaal)}", ""]
    if mogelijk_betaald:
        mb_tot = sum((D(_get(i, "open_amount")) for i in mogelijk_betaald), Decimal(0))
        refs = ", ".join(str(_get(i, "reference") or "-") for i in mogelijk_betaald)
        tekst += [f"Voor {len(mogelijk_betaald)} {'factuur' if len(mogelijk_betaald) == 1 else 'facturen'} ({refs}; samen {eur(mb_tot)}) "
                  "zien wij een betaling die er mogelijk bij hoort en die nog niet is afgepunt. Wij vermelden die daarom niet als te betalen "
                  "en laten dit nakijken.", ""]
    if negatieven:
        tekst += [_neg_tekst(soort, len(negatieven), abs(neg_totaal), je_u), "",
                  f"Netto openstaand na aftrek: {eur(totaal + neg_totaal)}", ""]
    tekst += [*vragen, ""]
    if handleiding_in_mail:
        tekst += [handleiding_tekst_kort(), ""]
    tekst += ["Met vriendelijke groeten,", sig]
    if edition.REQUIRE_ATTRIBUTION:
        tekst += ["", ATTRIBUTION]
    tekst_s = "\n".join(tekst)

    stijl = intern_rules.MAIL_STIJL if (edition.INTERNAL_RULES and intern_rules) else MAIL_STIJL_B
    rows = "".join(
        f"<tr><td>{escape(str(_get(i, 'reference') or '-'))}</td><td>{_datum(_get(i, 'date'))}</td>"
        f"<td>{_datum(_get(i, 'due_date'))}</td><td style='text-align:right'>{eur(D(_get(i, 'open_amount')))}</td></tr>"
        for i in open_posten)
    h = [f"<div style=\"{stijl}\">", f"<p>{escape(aanhef)}</p>", f"<p>{escape(intro)}</p>",
         "<table style='border-collapse:collapse' border='1' cellpadding='4'>"
         "<tr><th>Factuur</th><th>Factuurdatum</th><th>Vervaldatum</th><th>Openstaand</th></tr>"
         f"{rows}<tr><td colspan='3'><strong>Totaal openstaand</strong></td>"
         f"<td style='text-align:right'><strong>{eur(totaal)}</strong></td></tr></table>"]
    if mogelijk_betaald:
        h.append(f"<p>Voor {len(mogelijk_betaald)} {'factuur' if len(mogelijk_betaald) == 1 else 'facturen'} ({escape(refs)}; samen {eur(mb_tot)}) "
                 "zien wij een betaling die er mogelijk bij hoort en die nog niet is afgepunt. Wij vermelden die daarom niet als te betalen "
                 "en laten dit nakijken.</p>")
    if negatieven:
        h.append(f"<p>{escape(_neg_tekst(soort, len(negatieven), abs(neg_totaal), je_u))}</p>"
                 f"<p>Netto openstaand na aftrek: {eur(totaal + neg_totaal)}</p>")
    h += [f"<p>{escape(v)}</p>" for v in vragen]
    if handleiding_in_mail:
        h.append(f"<p>{escape(handleiding_tekst_kort())}</p>")
    h += ["<p>Met vriendelijke groeten,<br>" + escape(sig) + "</p>"]
    if edition.REQUIRE_ATTRIBUTION:
        h.append(f"<p style='font-size:9pt;color:#666666'>{ATTRIBUTION}</p>")
    h.append("</div>")
    html_s = "".join(h)

    cc_voorstel = intern_rules.CC_VOORSTEL if (edition.INTERNAL_RULES and intern_rules) else None
    res: dict[str, Any] = {
        "status": "CONCEPT, niet verzonden", "relatie": relatie, "soort": soort, "onderwerp": onderwerp,
        "tekst": tekst_s, "html": html_s, "totaal_openstaand": float(totaal.quantize(Decimal("0.01"))),
        "aantal_posten": len(open_posten), "mogelijk_reeds_betaald": len(mogelijk_betaald), "negatieve_posten_totaal": float(neg_totaal.quantize(Decimal("0.01"))),
        "bijlage": None,
        "bronnen": ["Accounting.OutstandingDebtorItems" if soort == "debiteuren" else "Accounting.OutstandingCreditorItems"],
        "opmerking": "Nazien door de gebruiker vóór verzending. Deze plugin verstuurt nooit mail.",
    }
    if edition.INTERNAL_RULES and intern_rules:
        res.update(intern_rules.extra_velden())
    if edition.REQUIRE_ATTRIBUTION:
        res["vermelding"] = ATTRIBUTION
    ensure(res["tekst"] + res["html"], edition.REQUIRE_ATTRIBUTION)

    if eml_map:
        d = Path(eml_map).expanduser()
        d.mkdir(parents=True, exist_ok=True)
        msg = EmailMessage()
        msg["Subject"] = onderwerp
        if aan:
            msg["To"] = aan
        cc_val = cc or cc_voorstel
        if cc_val:
            msg["Cc"] = cc_val
        msg["Date"] = format_datetime(datetime.now().astimezone())
        msg["X-Unsent"] = "1"           # Outlook opent het bestand als concept
        if edition.REQUIRE_ATTRIBUTION:
            msg["X-Generated-By"] = ATTRIBUTION
        msg.set_content(tekst_s)
        msg.add_alternative(html_s, subtype="html")
        safe = "".join(ch if ch.isalnum() else "-" for ch in relatie).strip("-")[:40] or "relatie"
        p = d / f"concept-{soort}-{safe}-{_d(peildatum).isoformat()}.eml"
        p.write_bytes(bytes(msg))
        res["eml_pad"] = str(p)
    return res
