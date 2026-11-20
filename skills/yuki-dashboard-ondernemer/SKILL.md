---
name: yuki-dashboard-ondernemer
description: Gebruik wanneer een ondernemer zijn eigen Yuki-administratie wil raadplegen en er een dashboard of overzicht van wil (omzet, kosten, resultaat, open klanten en leveranciers, liquiditeit, vergelijking met vorige periode). Alleen lezen.
---

# Yuki-dashboard voor ondernemers

Powered by FISCALCI Accounting & Tax (Askin Alci)

Bedoeld voor Belgische ondernemers; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Buiten België: verifieer zelf de lokale regels.

## Regels
- Alleen lezen. Zet `YUKI_WRITE_ENABLED` nooit aan en boek niets.
- Geen fiscaal advies: zeg erbij dat de cijfers uit Yuki komen en door de boekhouder nagekeken moeten worden.
- Verzin geen cijfers; elke waarde komt uit een tool en je noemt de bron (`bronnen`).
- Open bedrag kleiner dan 0 is een negatief open bedrag (creditnota, betaling, voorschot): vermeld het als na te gaan, geen conclusie.
- Verstuur niets en zet geen klantgegevens in diensten van derden.

## Werkwijze
1. `yuki_administraties` (controleer dat het de juiste administratie is).
2. `yuki_dashboard_kpis` met `jaar`, optioneel `periode` en `vergelijk_vorige_periode`.
3. Verdiep op vraag: `yuki_ouderdom_openstaande_posten`, `yuki_top_relaties`, `yuki_marge_kostenstructuur`, `yuki_periodevergelijking`.
4. Presenteer als dashboard (pagina/canvas indien beschikbaar) met: omzet, kosten, resultaat, marge, liquide middelen, open debiteuren en crediteuren (totaal en vervallen), btw-indicatie. Markeer vervallen bedragen.
5. Wil de gebruiker bestanden voor Excel of een BI-tool: `yuki_export_dataset` met een `export_map`.
