"""Handleiding: wat betekenen positieve en negatieve saldi bij debiteuren en crediteuren?

Algemeen en zonder juridische claims. Waar een regel uit officiële bron moet komen staat
'verifieer actuele regel'.
"""
from __future__ import annotations

BE_AFBAKENING = ("Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). "
                 "Gebruik buiten België: verifieer zelf de lokale regels. Wettelijke verwijzingen komen alleen uit officiële bronnen; anders staat er "
                 "'verifieer actuele regel'.")

TEKENCONVENTIE = (
    "Tekenconventie (verifieer in je eigen dossier): "
    "(1) Openstaande posten (Accounting.OutstandingDebtorItems / OutstandingCreditorItems): "
    "live waarneming (20/11/2026, één dossier, alleen tekens bekeken): bij debiteuren en crediteuren is OpenAmount "
    "positief = nog open (debiteur: te ontvangen; crediteur: te betalen), terwijl het grootboeksaldo van de "
    "crediteurenrekening een creditsaldo (negatief) was. Open posten staan dus in 'openstaande' richting en niet in het "
    "teken van het grootboek. Een negatieve open post kan zowel bij debiteuren als bij crediteuren betekenen: (a) een "
    "creditnota, (b) een ontvangen of uitgevoerde betaling waar geen (gekoppelde) factuur tegenover staat (los staande betaling), "
    "(c) een voorschot, (d) een te veel of dubbel betaalde som. Meestal gaat het om (b): een betaling zonder factuur; "
    "de andere gevallen komen minder vaak voor. Het teken alleen zegt niet welke; zie de omschrijving en "
    "het documenttype in Yuki. De Yuki-documentatie beschrijft het teken niet; controleer jouw dossier. Toont het voor "
    "crediteuren negatieve bedragen voor te betalen facturen, zet dan YUKI_CREDITOR_SIGN=negatief (standaard: positief, "
    "bevestigd in de live waarneming). "
    "(2) Proef- en saldibalans (Accounting.GLAccountBalance): saldo = debet - credit; een positief saldo is een "
    "debetsaldo, een negatief saldo een creditsaldo (opbrengsten dus negatief). Live bevestigd: debetrekeningen (klanten) positief, crediteuren negatief. "
    "Niet uitdrukkelijk beschreven in de officiële documentatie. "
    "(3) Yuki bepaalt het documenttype van een ingelezen e-factuur uit documenttype en teken van het bedrag samen "
    "(officiële Yuki-supportpagina over creditnota's): een creditnota kan als factuur binnenkomen als het teken "
    "in de XML omgekeerd is. Een negatieve post kan dus ook een foute boeking zijn."
)

SECTIES_NL = [
    ("Debiteuren (klanten)", [
        ("Positief saldo of positieve open post",
         "De klant moet nog betalen. Controleer eerst of de factuur al vervallen is (vervaldatum) en of er een "
         "betaling onderweg is. Actie: vriendelijke herinnering; bij blijvende wanbetaling een tweede aanmaning. "
         "Ingebrekestelling of invordering: verifieer actuele regel en raadpleeg de boekhouder of een jurist."),
        ("Negatief saldo of negatieve open post",
         "Meestal een betaling van de klant waar geen (gekoppelde) factuur tegenover staat: de factuur ontbreekt in de "
         "boekhouding, is nog niet geboekt of is niet aan de betaling afgepunt. Minder vaak: (a) een creditnota die nog niet "
         "verrekend is, (c) een voorschot, (d) een te veel of dubbel betaalde som. "
         "Actie per geval: (b) de factuur nakijken of laten bezorgen, nagaan of ze nog geboekt moet worden en de betaling "
         "laten afpunten tegen de juiste factuur (door de boekhouder te laten corrigeren); eerst controleren of er een "
         "afpuntingsvoorstel is (yuki_afpuntingsvoorstellen); (a) verrekenen met een openstaande factuur of terugbetalen na "
         "akkoord; (c) voorschot koppelen aan de eindfactuur of verrekenen; (d) bankafschrift naast de factuur leggen, daarna "
         "terugbetalen of verrekenen na akkoord van de klant en de boekhouder; bij twijfel bij de klant navragen."),
        ("Saldo nul maar toch een open post",
         "Positieve en negatieve posten die elkaar opheffen maar nog niet aan elkaar gekoppeld zijn. Actie: laat "
         "de boekhouder de posten afletteren."),
    ]),
    ("Crediteuren (leveranciers)", [
        ("Positieve open post",
         "Je moet de leverancier nog betalen. Actie: betaal tijdig volgens de afgesproken betalingstermijn "
         "(verifieer actuele regel voor wettelijke termijnen); controleer of de factuur klopt (bestelling, bedrag, btw) "
         "vóór betaling."),
        ("Negatieve open post",
         "Meestal een uitgevoerde betaling aan de leverancier waar geen (gekoppelde) factuur tegenover staat: de factuur is "
         "nog niet ontvangen of geboekt, of niet aan de betaling afgepunt. Minder vaak: (a) een creditnota van de leverancier, "
         "(c) een voorschot, (d) een te veel of dubbel betaalde som. "
         "Actie per geval: (b) de factuur opvragen bij de leverancier of laten bezorgen, daarna boeken en laten afpunten "
         "(door de boekhouder); eerst nagaan of een afpuntingsvoorstel bestaat (yuki_afpuntingsvoorstellen); (a) creditnota "
         "controleren en verrekenen of opvragen; (c) voorschot koppelen aan de factuur; (d) bankafschrift controleren en bij de "
         "leverancier een terugbetaling of verrekening navragen."),
        ("Onverwacht groot of ongewoon saldo",
         "Kan wijzen op een foute boeking (verkeerde leverancier, verkeerd teken, verkeerd boekjaar). Actie: laat "
         "de boekhouder de boeking nakijken en zo nodig corrigeren. Corrigeer zelf niets in Yuki via deze plugin: "
         "ze leest alleen."),
    ]),
    ("Samengevat per situatie", [
        ("Herinneren", "Positieve debiteurenpost, net vervallen: vriendelijke herinnering."),
        ("Aanmanen", "Positieve debiteurenpost, ruim vervallen na herinnering: tweede aanmaning; juridische stappen: verifieer actuele regel."),
        ("Verrekenen / afpunten", "Negatieve post (creditnota, betaling of voorschot) en positieve post bij dezelfde relatie: laat de boekhouder afpunten tegen de juiste factuur."),
        ("Terugbetalen", "Blijvend negatief bedrag zonder open facturen en geen losse betaling of voorschot meer: terugbetaling na controle en akkoord."),
        ("Factuur opvragen of bezorgen", "Meest voorkomend: betaling zonder factuur. Crediteur: factuur opvragen bij de leverancier. Debiteur: factuur nakijken of laten bezorgen."),
        ("Navragen", "Type onduidelijk: bij de klant of leverancier navragen en de boekhouder laten nakijken of de factuur nog geboekt moet worden."),
        ("Creditnota opvragen", "Crediteur met negatieve post waarvan de creditnota in het dossier ontbreekt."),
        ("Dubbele betaling nagaan", "Twee betalingen voor dezelfde factuur: bankafschrift en factuurreferentie vergelijken."),
        ("Foute boeking laten corrigeren", "Teken, relatie of bedrag klopt niet: meld het aan de boekhouder."),
    ]),
]


def handleiding_md(titel: str = "Handleiding saldi debiteuren en crediteuren") -> str:
    out = [f"# {titel}", "", BE_AFBAKENING, "", TEKENCONVENTIE, ""]
    for kop, items in SECTIES_NL:
        out += [f"## {kop}", ""]
        for k, t in items:
            out += [f"**{k}.** {t}", ""]
    out.append("Algemene uitleg, geen juridisch advies. Wettelijke termijnen en invorderingsstappen: verifieer actuele regel.")
    return "\n".join(out) + "\n"


def handleiding_tekst_kort() -> str:
    """Korte tekstversie voor onderaan een herinneringsmail (toelichting, geen bijlage)."""
    return (
        "Toelichting bij de bedragen: een positief bedrag is nog te betalen. Een negatief bedrag is geen schuld; het verlaagt "
        "het totaal. Meestal is het een betaling waar bij ons nog geen (gekoppelde) factuur tegenover staat; minder vaak een "
        "creditnota, een voorschot of een te veel betaalde som. Wij laten dit nakijken en koppelen het aan de juiste factuur. "
        "Klopt een bedrag volgens u niet, of hebt u al betaald, laat het ons dan weten met de betaaldatum."
    )


def handleiding_html_body(titel: str = "Handleiding saldi debiteuren en crediteuren") -> str:
    from html import escape
    parts = [f"<h1>{escape(titel)}</h1>", f"<p>{escape(BE_AFBAKENING)}</p>", f"<p>{escape(TEKENCONVENTIE)}</p>"]
    for kop, items in SECTIES_NL:
        parts.append(f"<h2>{escape(kop)}</h2>")
        for k, t in items:
            parts.append(f"<p><strong>{escape(k)}.</strong> {escape(t)}</p>")
    parts.append("<p class='klein'>Algemene uitleg, geen juridisch advies. Wettelijke termijnen en "
                 "invorderingsstappen: verifieer actuele regel.</p>")
    return "\n".join(parts)
