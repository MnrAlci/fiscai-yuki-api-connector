---
name: fiscai-yuki-api-connector
description: Use when you need Yuki accounting figures (administrations, balances, open debtor and creditor items, revenue, dashboard, reminder drafts) through the FISCAi Yuki API Connector plugin; read-only with a hard daily call limit. Gebruik voor Yuki-cijfers en conceptmails voor openstaande posten.
---

# FISCAi Yuki API Connector

Powered by FISCALCI Accounting & Tax (Askin Alci)

Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.

## Wanneer gebruiken
Voor elke vraag die Yuki-gegevens nodig heeft: cijfers van een administratie, openstaande posten, ouderdomsanalyse, DSO/DPO, periodevergelijking, dashboard of een conceptmail voor openstaande facturen.

## Harde regels
- **Writing is OFF by default.** Without `YUKI_WRITE_ENABLED=ja` the plugin cannot book, upload or change anything. When enabled: never bulk, never automatic; one booking per explicit user confirmation (token + hash + confirmation 'ja'); show the proposal first (Belgian MAR and VAT, verify the current rule).
- **Daglimiet: standaard 900 calls per domein per dag.** Yuki: 1000 calls per domein per dag zijn gratis. Instelbaar met `YUKI_DAILY_LIMIT`; boven 1000 alleen met `YUKI_DAILY_LIMIT_APPROVAL` en dan kunnen kosten volgen. Zonder bevestiging geldt maximaal 1000.
- Controleer `yuki_status` bij grote opdrachten. Een cache-hit kost niets; `vernieuwen: true` kost een call; elke pagina van een gepagineerde set is één call.
- Gebruik bij voorkeur eerst de analysetools in plaats van ruwe sets.

## Toegangsniveau
`YUKI_ACCESS_LEVEL=portaal` (alle administraties met een accountantsportaal-sleutel) of `domein` (sleutel per domein, parameter `domein`). Kies de administratie per call met `administratie`.

## Vertrouwelijkheid
Boekhoudgegevens zijn vertrouwelijk. Toon in de chat alleen wat nodig is, gebruik voor voorbeelden placeholders zoals [Voorbeeld] en [Klant A], en schrijf exports alleen in een map die de gebruiker opgeeft.

## Conceptmails
`yuki_herinneringsmail` bouwt een concept (tekst, HTML, optioneel .eml) en verstuurt nooit. Laat de gebruiker het concept nakijken en zelf verzenden. Handtekening instelbaar met `YUKI_MAIL_SIGNATURE`.

## Handleiding saldi (kort)
Tekenconventie, in één live dossier bevestigd (zie handleiding), verifieer in het eigen dossier:
- Debiteuren: positief = klant moet nog betalen (herinneren, aanmanen). Negatief = geen schuld maar na te gaan: (a) creditnota, (b) betaling die nog niet aan een factuur is afgepunt, (c) voorschot, (d) te veel of dubbel betaald. Doen: betaling laten afpunten tegen de juiste factuur (boekhouder), nagaan of de factuur nog geboekt moet worden, verrekenen, terugbetalen of bij de klant navragen.
- Crediteuren: positief = nog te betalen. Negatief = na te gaan: (a) creditnota, (b) uitgevoerde betaling nog niet afgepunt, (c) voorschot, (d) te veel of dubbel betaald. Doen: laten afpunten tegen de juiste factuur (boekhouder), nagaan of de factuur nog geboekt moet worden, verrekenen, creditnota opvragen of bij de leverancier navragen. Toont uw dossier het omgekeerde, zet `YUKI_CREDITOR_SIGN=negatief`.
- Proefbalans: saldo = debet min credit; opbrengsten zijn dus negatief.
- Foute boeking? Laat de boekhouder corrigeren in Yuki; de plugin kan een boeking niet terugdraaien (zie `docs/BOEKINGSWORKFLOW.md`).
Wettelijke termijnen of invorderingsstappen: verifieer actuele regel. Volledige tekst: `docs/handleiding-saldi.md`.

## Afpuntingscheck en opslaglocatie
- `yuki_afpuntingsvoorstellen`: stel de gebruiker voor een afpuntingscheck te doen zodra er negatieve open posten zijn (meestal betalingen zonder gekoppelde factuur). De tool zoekt 1-op-1 (gelijk bedrag of binnen tolerantie), meerdere betalingen voor één factuur, één betaling voor meerdere facturen en lagere-zekerheidstreffers over relaties heen (o.a. dubbele relatiefiche). Elk voorstel toont relaties, documenten, datums, bedragen, verschil, zekerheid met reden en voorgestelde actie. Alleen voorstellen: de plugin punt nooit zelf af. Export als CSV en HTML met `export_map`.
- Negatieve open bedrag: meestal een betaling zonder (gekoppelde) factuur. Crediteur: factuur opvragen of laten bezorgen. Debiteur: factuur nakijken of laten bezorgen. Minder vaak creditnota, voorschot of te veel betaald.
- **De gebruiker kiest waar het permanente dossier van de cliënt bewaard wordt.** Gebruik `yuki_opslag_status`; zonder keuze vraag je het de gebruiker en bewaar je het antwoord met `yuki_opslag_instellen` (lokaal, OneDrive, SharePoint, Google Drive, Dropbox, dossierbeheerpakket of geen). Er is geen standaardlocatie. Tools die exports maken (`yuki_dashboard`, `yuki_herinneringsmail`, `yuki_handleiding_saldi`, `yuki_afpuntingsvoorstellen`) bewaren enkel als de gebruiker in die call `opslaan: true` vraagt. Lokaal schrijft de plugin zelf (geen Yuki-schrijfactie); voor cloud krijg je een opslagvoorstel en instructie voor de gekozen connector, nooit een automatische upload. Betalende diensten worden als zodanig gemarkeerd.

## Boekingsworkflow (optioneel, standaard UIT)
- **Boeken in Yuki betekent backoffice-status Afgehandeld.** Workflowdocumenten (aankoop of verkoop) handel je af via 'Afhandelen' in de Yuki-backoffice (de gebruiker of een eigen procedure); de plugin weigert ze als journaalpost (een journaalpost geeft een dubbele kost). `ProcessJournal` is alleen voor echte memoriaalposten.
- Schrijven in Yuki vereist `YUKI_WRITE_ENABLED=ja` in de omgeving van de MCP-server; zet die nooit zelf en nooit globaal. Zonder die variabele doen de `yuki_boeking_*`-tools niets in Yuki.
- Voor een workflowdocument (aankoop of verkoop) geeft `yuki_boeking_voorstel` het voorstel en de dubbelcontrole als invoer, maar nooit een token; `yuki_boeking_bevestigen` weigert zo'n voorstel (harde blokkade).
- Volgorde: `yuki_boeking_voorstel` (volgend document of wachtrekeningregel, Belgisch MAR en btw) → toon het voorstel → de gebruiker past aan of bevestigt → `yuki_boeking_bevestigen` met token, voorstel_hash en `bevestiging='ja'`. Eén boeking per bevestiging, nooit bulk of automatisch; eerst eventueel `dry_run: true`.
- Dubbelcontrole vóór elk token: 'geen bestaande boeking gevonden', 'mogelijk al geboekt' of 'al geboekt' (of controle mislukt) geeft geen token. Deblokkeren alleen op uitdrukkelijke vraag van de gebruiker met `deblokkeren: true` en `deblokkeer_reden` (komt in het auditlog).
- Btw-bedrag 0 of ontbrekend: vraag de reden (`btw_nul_reden`: verlegd, intracommunautair, vrijgesteld, buiten_toepassingsgebied, kleine_onderneming, prive_niet_aftrekbaar, ander met toelichting). Bij verlegd of intracommunautaire verwerving laat je de gebruiker de btw-regels zelf bevestigen of aanvullen (`btw_regels_bevestigd`, `btw_extra_regels`); verzin niets. Verifieer actuele regel.
- Deze editie bevat geen eigen kantoorregels. Pas de btw-aftrekregels zelf toe volgens de officiële bron (FOD Financiën); verifieer actuele regel.
- Zie `docs/BOEKINGSWORKFLOW.md`. Workflowdocumenten zijn geblokkeerd voor `ProcessJournal`; echte memoriaalposten zijn nog niet live getest: laat de boekhouder de eerste boekingen in Yuki nakijken.

## Voorbeeld
"Geef de ouderdomsanalyse van de debiteuren van [Voorbeeld] per 30/11/2026": roep `yuki_ouderdom_openstaande_posten` aan met `administratie: "[Voorbeeld]"`, `soort: "debiteuren"`, `peildatum: "2026-11-30"` en vermeld de bronmethode in het antwoord.
