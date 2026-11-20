---
name: yuki-portfolio-accountant
description: Gebruik wanneer een accountant met een portaalsleutel een overzicht over meerdere dossiers wil (omzet, kosten, resultaat, liquide middelen, open posten per dossier). Alleen lezen.
---

# Yuki-portefeuilleoverzicht voor accountants

Powered by FISCALCI Accounting & Tax (Askin Alci)

Bedoeld voor Belgische accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Buiten België: verifieer zelf de lokale regels.

## Regels
- Alleen lezen. Zet `YUKI_WRITE_ENABLED` nooit aan en boek niets.
- Geen fiscaal advies: zeg erbij dat de cijfers uit Yuki komen en door de boekhouder nagekeken moeten worden.
- Verzin geen cijfers; elke waarde komt uit een tool en je noemt de bron (`bronnen`).
- Open bedrag kleiner dan 0 is een negatief open bedrag (creditnota, betaling, voorschot): vermeld het als na te gaan, geen conclusie.
- Verstuur niets en zet geen klantgegevens in diensten van derden.

## Werkwijze
1. `yuki_administraties` (portaalsleutel: alle bereikbare dossiers; vraag welke dossiers bedoeld zijn).
2. `yuki_portfolio_kpis` met `jaar` en de gekozen `administraties` (standaard max. 5, maximum 15; ongeveer 4 Yuki-calls per dossier, controleer `yuki_status`).
3. Verdiep op vraag: `yuki_ouderdom_openstaande_posten`, `yuki_top_relaties`, `yuki_marge_kostenstructuur`, `yuki_periodevergelijking`.
4. Presenteer een tabel per dossier plus totaal; vermeld fouten per dossier apart. Klantcijfers blijven op deze computer: deel ze niet met derden zonder toestemming van de klant.
5. Wil de gebruiker bestanden voor Excel of een BI-tool: `yuki_export_dataset` met een `export_map`.
