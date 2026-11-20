# FISCAi Yuki API Connector: volledige handleiding

> Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

Deze handleiding legt elke functie uit en geeft stap-voor-stapinstructies. De connector is een plugin voor Grok Bot (werkt ook in Copilot, Claude, Cursor, Windsurf en andere MCP-clients) die uw Yuki-boekhouding lokaal leest met uw eigen sleutel. Standaard is hij **alleen-lezen voor Yuki** en hij is geen officieel product van Yuki of Visma. De officiële Yuki-referentie is de [Yuki API Webservices Documentation](https://documenter.getpostman.com/view/12207912/UVCBB51L).

## 1. Installeren en eerste gebruik
1. U hebt Python 3.10 of hoger nodig en een Yuki API-sleutel (portaalsleutel of domeinsleutel).
2. Haal de code op en installeer de afhankelijkheden: `git clone <repository-url> fiscai-yuki-api-connector`, dan `cd fiscai-yuki-api-connector`, `python3 -m venv .venv`, `.venv/bin/pip install -r requirements.txt`.
3. Voeg de map toe aan Grok Bot als plugin en vul `YUKI_ACCESS_KEY` in via de eigen instellingen van Grok Bot. Zet de sleutel nooit in een bestand, een chat of de repository.
4. Vraag aan Grok Bot: "Voer `yuki_status` uit". Dat doet geen Yuki-call en bevestigt de installatie.
5. Op de opdrachtregel: `export YUKI_ACCESS_KEY=...` en dan `yuki-api-connector doctor`. Dat controleert Python, pakketten en variabelen en toont geen geheimen. Zonder installatie van het pakket: `python3 server/run_connector.py doctor`.

Belangrijke instellingen: `YUKI_ACCESS_KEY` (geheim), `YUKI_ACCESS_LEVEL` (`portaal` of `domein`), `YUKI_DAILY_LIMIT` (standaard 900 calls per domein per dag), `YUKI_DATA_DIR`. **Zet `YUKI_WRITE_ENABLED` nooit aan** tenzij u bewust de optionele boekingsworkflow wilt (zie punt 12).

## 2. Gebruiken vanuit een assistent
1. **Grok Bot (aanbevolen)**: installeer de plugin (punt 1) en vraag gewoon in gewone taal: "Geef me de ouderdom van de debiteuren van [Voorbeeld] BV op 30/11/2026."
2. **Andere MCP-clients**: registreer de server (opdracht, argumenten en omgeving) volgens de gids in `docs/clients/` voor Cursor, Claude Desktop, Claude Code, Copilot (VS Code), Windsurf of een generieke client. Gebruik de eigen geheimenopslag van de client voor de sleutel.
3. **Agents**: kant-en-klare agentdefinities staan in `agents/` (punt 10).

## 3. De tools per domein
Er zijn 70 tools (`yuki_*`). Alles is alleen-lezen voor Yuki, behalve de boekingsworkflow (groep "Boekingsworkflow", standaard uit) en `yuki_opslag_instellen`, dat enkel een lokale instelling wijzigt.

### Status en administraties

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_status` | Dagteller per domein, ingestelde daglimiet (standaard 900), toegangsniveau en antwoordcache. | ja |
| `yuki_administraties` | Alle administraties die met de sleutel bereikbaar zijn. | ja |
| `yuki_administratie_id` | Administratie-ID (GUID) bij een exacte administratienaam. | ja |
| `yuki_domeinen` | Alle domeinen die met deze sleutel bereikbaar zijn. | ja |
| `yuki_bedrijven` | Alle beschikbare administraties (Companies). | ja |
| `yuki_huidig_domein` | Het huidige Yuki-domein van de sessie. | ja |

### Boekhouding en saldi (lezen)

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_proefbalans` | Saldo per grootboekrekening op een datum (Accounting.GLAccountBalance[Fiscal/YearEnd]). | ja |
| `yuki_netto_omzet` | Netto-omzet in een periode (Accounting.NetRevenue[Fiscal]). | ja |
| `yuki_openstaande_posten` | Openstaande debiteuren of crediteuren, optioneel op een peildatum (Accounting.Outstanding{Debtor/Creditor}Items[ByDateOutstanding]). | ja |
| `yuki_grootboekmutaties` | Boekingen op één grootboekrekening (AccountingInfo.GetTransactionDetails). | ja |
| `yuki_rekeningschema` | Alle grootboekrekeningen (AccountingInfo.GetGLAccountScheme). | ja |
| `yuki_boekjaar_gewijzigd` | Laatste wijzigingsdatum van de boekingen in een boekjaar (AccountingInfo.GetFinancialYearModifiedDate). | ja |
| `yuki_jaartotalen` | Jaartotalen (MAR) en ratio's uit proef- en saldibalans en netto-omzet. | ja |
| `yuki_openstaande_posten_periode` | Openstaande debiteuren- of crediteurenposten met factuurdatum tussen twee data; optioneel met betaalreferentie. | ja |
| `yuki_grootboektransacties` | Transacties van één grootboekrekening in een periode (oudere Accounting-variant; zie ook yuki_grootboekmutaties). | ja |
| `yuki_controleer_open_post` | Open bedrag van één transactie via factuurnummer of ID (GUID). | ja |
| `yuki_startbalans` | Beginsaldo's per grootboekrekening voor een boekjaar. | ja |
| `yuki_periodetabel` | Startdatum van een boekjaar per administratie. | ja |
| `yuki_transacties_gepagineerd` | Grootboektransacties met paginering; haalt standaard alle pagina's op (max_paginas begrenst). | ja |
| `yuki_aangepaste_betaalmethodes` | Alle aangepaste betaalmethodes. | ja |
| `yuki_rgs_schema` | Rekeningschema met RGS-codes (Nederlandse referentie; in België meestal niet gebruikt). | ja |
| `yuki_projecten` | Projecten (GetProjects of GetProjectsAndID). | ja |
| `yuki_projectsaldo` | Saldo van een project per grootboekrekening. | ja |
| `yuki_contact_standaardwaarden` | Standaardwaarden van een contact in een administratie. | ja |
| `yuki_verkoopitems` | Verkoopartikelen van een administratie. | ja |

### Analyses

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_ouderdom_openstaande_posten` | Ouderdom (niet vervallen, 0-30, 31-60, 61-90, >90 dagen) van openstaande debiteuren/crediteuren; negatieve open bedragen apart (neutraal gelabeld, type enkel indien Yuki  | ja |
| `yuki_dso_dpo` | Gemiddelde betaaltermijn: DSO = debiteuren/omzet x dagen, DPO = crediteuren/inkopen (klasse 60) x dagen, vanaf 1 januari. | ja |
| `yuki_top_relaties` | Grootste openstaande saldi per relatie. | ja |
| `yuki_periodevergelijking` | Omzet, kosten en resultaat voor een maand, kwartaal of jaar, vergeleken met de vorige periode en/of hetzelfde van vorig jaar. | ja |
| `yuki_marge_kostenstructuur` | Brutomarge, nettomarge en kosten per MAR-klasse (60-68) in een periode. | ja |
| `yuki_liquiditeit` | Current ratio, cash ratio, werkkapitaal, solvabiliteit op een datum. | ja |
| `yuki_uitschieters` | Statistische uitschieters (mediaan/MAD) en mogelijk dubbele boekingen op één grootboekrekening. | ja |
| `yuki_afpuntingsvoorstellen` | Zoekt voorstellen om negatieve open posten (meestal betalingen zonder gekoppelde factuur) af te punten: 1-op-1 (gelijk bedrag of binnen tolerantie), meerdere betalingen v | ja |

### Dashboards en kerncijfers

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_dashboard` | Dashboard met omzet, kosten, resultaat, liquiditeit, openstaande debiteuren/crediteuren met ouderdom en btw-saldo-indicatie. | ja |
| `yuki_dashboard_kpis` | Compacte kerncijfers van één administratie voor een eigen dashboard: omzet, kosten, resultaat, marge, liquide middelen, liquiditeit, open debiteuren en crediteuren (totaa | ja |
| `yuki_portfolio_kpis` | Kerncijfers per administratie over meerdere dossiers heen (omzet, kosten, resultaat, liquide middelen, open debiteuren en crediteuren) voor een portfolio-overzicht. | ja |

### Export en dossieroverdracht

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_export_dataset` | Schrijft een dataset met vast, gedocumenteerd schema (kpis, saldi, openstaande_posten) als lokaal bestand in een map naar keuze, voor Power BI, Qlik, Tableau, Metabase, E | ja |
| `yuki_dossier_transfer_export` | Exporteert per boekjaar naar een map: rekeningschema, proefbalans (slot, begin, jaarafsluiting), startbalans, grootboekmutaties, openstaande posten op balansdatum, contac | ja |

### Concepten, uitleg en lokale opslag

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_herinneringsmail` | Bouwt een CONCEPTmail voor één relatie met openstaande posten. | ja |
| `yuki_handleiding_saldi` | Uitleg over positieve en negatieve saldi bij debiteuren en crediteuren en wat te doen. | ja |
| `yuki_opslag_status` | Toont welke opslaglocatie de gebruiker koos voor het permanente dossier (per administratie) en welke koppeling daarvoor nodig is. | ja |
| `yuki_opslag_instellen` | Bewaart de keuze van de gebruiker voor het permanente dossier in de lokale configuratie (per administratie, of voor alle administraties als de gebruiker dat uitdrukkelijk | nee (lokaal of vergrendeld) |

### Btw

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_btw_aangiftes` | Lijst van btw-aangiften voor een jaar (lezen, geen indiening). | ja |
| `yuki_btw_codes` | Actieve btw-codes van een administratie. | ja |

### Archief (documenten, alleen metadata)

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_archief_mappen` | Alle archiefmappen. | ja |
| `yuki_archief_mappen_aantallen` | Aantallen per map voor een jaar. | ja |
| `yuki_archief_tabs` | Tabs van een archiefmap. | ja |
| `yuki_archief_documenten` | Documentmetadata, gepagineerd (alleen metadata, geen bestandsinhoud). | ja |
| `yuki_archief_documenten_in_map` | Documentmetadata in een map. | ja |
| `yuki_archief_documenten_in_tab` | Documentmetadata in een tab. | ja |
| `yuki_archief_documenten_per_type` | Documentmetadata per documenttype. | ja |
| `yuki_archief_gewijzigd_per_type` | Sinds een datum gewijzigd. | ja |
| `yuki_archief_gewijzigd_in_map` | Sinds een datum gewijzigd. | ja |
| `yuki_archief_zoeken` | Zoeken in documentmetadata. | ja |
| `yuki_archief_document` | Metadata van één document. | ja |
| `yuki_archief_document_xml` | Herkende gegevens (XML) van een document, geen bestand. | ja |
| `yuki_archief_document_paginas` | Aantal pagina-afbeeldingen. | ja |
| `yuki_archief_betaalmethodes` | Betaalmethodes. | ja |
| `yuki_archief_kostencategorieen` | Kostencategorieën. | ja |
| `yuki_archief_valuta` | Valuta's. | ja |
| `yuki_archief_menu` | Menustructuur van het archief. | ja |
| `yuki_archief_projecten` | Projecten van een administratie. | ja |

### Contacten

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_contacten_zoeken` | Contacten zoeken; gepagineerd. | ja |
| `yuki_klanten_leveranciers` | Klanten en/of leveranciers; gepagineerd. | ja |

### Backoffice en workflow

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_backoffice_workflow` | De workflow (te verwerken documenten) van een administratie (lezen). | ja |
| `yuki_afhandeling_controle` | Leest Backoffice.GetWorkflow en controleert of een document (document_id uit het boekingsvoorstel, 'D:<id>') niet meer in de workflow staat, nadat het in de Yuki-backoffi | ja |

### Boekingsworkflow (standaard UIT, schrijft in Yuki)

| Tool | Wat het doet | Alleen lezen |
|---|---|---|
| `yuki_boeking_voorstel` | Toont het volgende onbehandelde item (document uit de documentworkflow of bankverrichting op de wachtrekening) met een boekingsvoorstel (rekening, btw-code, relatie, bedr | nee (lokaal of vergrendeld) |
| `yuki_boeking_overslaan` | Markeert een item lokaal als overgeslagen zodat het niet meer als volgend item verschijnt. | nee (lokaal of vergrendeld) |
| `yuki_boeking_bevestigen` | SCHRIJFT één journaalpost in Yuki (Accounting.ProcessJournal) na uitdrukkelijke bevestiging van de gebruiker voor precies dit voorstel. | nee (lokaal of vergrendeld) |
| `yuki_boeking_status` | Toont of de boekingsworkflow aanstaat, de vervaltijd van tokens, het dagmaximum en het aantal boekingen vandaag. | ja |


## 4. Dashboards en kerncijfers
1. Begin met `yuki_dashboard_kpis` (administratie, jaar, optioneel periode `kwartaal:2` of `maand:5`, optioneel vergelijking met de vorige periode): omzet, kosten, resultaat, marge, liquide middelen, open debiteuren en crediteuren (totaal en vervallen), DSO/DPO en een btw-indicatie.
2. Accountants gebruiken `yuki_portfolio_kpis` voor meerdere administraties (standaard 5, maximum 15; ongeveer 4 Yuki-calls per administratie).
3. `yuki_dashboard` toont een widget en kan een statisch HTML-bestand naar een map van uw keuze schrijven.
4. Opdrachtregel: `yuki-api-connector dashboard --administratie "[Voorbeeld] BV" --jaar 2026 --vergelijk --out kpis.json`. Met `--dry-run` ziet u het plan zonder calls.
5. Ga dieper op aanvraag: ouderdom (`yuki_ouderdom_openstaande_posten`), top relaties, marge, liquiditeit, periodevergelijking, uitschieters.

## 5. Exportlaag (CSV, JSON, xlsx, Parquet)
1. Vraag Grok Bot om te exporteren, of voer uit: `yuki-api-connector export --dataset kpis --administratie "[Voorbeeld] BV" --jaar 2026 --format csv,xlsx --out ./export`. Datasets: `kpis`, `saldi`, `openstaande_posten` (met `--soort debiteuren|crediteuren`).
2. De bestanden hebben een vast schema (zie `docs/EXPORT-SCHEMA.md`); Parquet vraagt het optionele `pyarrow`.
3. Laad de bestanden in uw tools: Power BI, Excel, Looker Studio, Metabase, Streamlit en andere (gidsen in `docs/integrations/`). De voorbeelden gebruiken enkel `[Voorbeeld]`-gegevens.
4. CSV is UTF-8; Excel met Belgische instellingen vraagt door de decimale komma soms om de importwizard.

## 6. Opdrachtregel
| Opdracht | Doel |
|---|---|
| `serve` | start de MCP-server (stdio; optioneel `--http` enkel op localhost) |
| `doctor [--online]` | controleer de omgeving (en één Yuki-call met `--online`) |
| `tools [--names-only]` | lijst van de tools |
| `call TOOL --args '{...}'` | roep één alleen-lezen tool aan |
| `export`, `dashboard` | exports en kerncijfers (punt 4 en 5) |
| `workflows plan | run | list | init` | automatisering (punt 8) |
| `transfer export` | dossieroverdracht per boekjaar (punt 9) |
| `config init` | schrijf een voorbeeld-`.env` met plaatshouders |
| `version`, `completion bash|zsh|powershell` | versie en shell-aanvulling |

Gemeenschappelijke opties: `--json`, `--quiet`, `--verbose`, `--log-level`, `--log-format json`, `--env-file`, `--config` en `--profile`, `--hooks`, `--dry-run`. Voorrang van instellingen: opdrachtregel, dan omgeving, dan bestand; configbestanden bevatten nooit geheimen. Exitcodes: 0 ok, 1 algemeen, 2 gebruik, 3 configuratie, 4 tool-/Yuki-fout, 5 netwerk, 6 geweigerd. Details: `docs/CLI.nl.md`.

## 7. Hooks (optioneel, standaard uit)
1. Kopieer `examples/hooks/hooks.example.toml` en zet `enabled = true`.
2. Kies events: `pre_call`, `post_call`, `on_error`, `on_export`, elk met een lokale opdracht (een lijst, geen shell) of een Python-functie.
3. Start met `--hooks BESTAND` of stel `YUKI_HOOKS_FILE` in.
4. Hooks krijgen nooit geheimen, breken nooit een call en draaien met een minimale omgeving. Voorbeelden: export kopiëren, auditlog, webhook, documentgenerator. Details: `docs/HOOKS.nl.md`.

## 8. Automatisering en herinneringen
1. `yuki-api-connector workflows init --path workflows.toml` schrijft een voorbeeldconfiguratie met `[Voorbeeld]`-gegevens.
2. Kies een agenda-adapter (ICS-bestand of link, Microsoft Graph, Google Calendar), uw klanten (herkenning op trefwoord, e-mail of domein), uw overzichtssjabloon en uw terugkerende verplichtingen. De deadlines in het voorbeeld zijn **voorbeelden gemarkeerd met "verifieer actuele regel"**; controleer de officiële bron.
3. `workflows list` toont wat is ingesteld; `workflows plan` toont wat er aankomt (geen Yuki-calls); `workflows run --dry-run` is hetzelfde zonder te schrijven.
4. `workflows run` schrijft een overzicht (Markdown en JSON) per vergadering twee dagen vooraf (instelbaar) en per verplichting die aankomt, toont de ontbrekende documenten en maakt een **concept** van een herinneringsmail.
5. Mails worden standaard nooit verstuurd. Verzenden vraagt `allow_send = true`, `--send` en een bevestiging per run, en enkel de SMTP-adapter kan versturen. Verzenden naar klanten is uw eigen verantwoordelijkheid.
6. Plan het met cron, Windows Taakplanner, GitHub Actions (versleutelde secrets), n8n, Zapier, Power Automate of een Grok Bot-routine. Details en voorbeelden: `docs/AUTOMATION.nl.md`.

## 9. Dossieroverdracht per boekjaar
1. Schat: `yuki-api-connector transfer export --administration "[Voorbeeld] BV" --fiscal-year 2025 --out ./overdracht --estimate-only`.
2. Uitvoeren: voeg per jaar één `--fiscal-year` toe (of `--all-years`), eventueel `--zip`, `--include-documents` en `--all-accounts`. Boven de drempel bevestigt u met `JA` (of `--yes`).
3. Stopt het daglimiet de run, herhaal dan later dezelfde opdracht: ze hervat vanaf het checkpoint.
4. Lees `CONTROL.md` en `MANIFEST.json` in elke jaarmap en de `README.md` bovenaan, geschreven voor de ontvangende boekhouder.
5. Draag veilig over en let op de professionele punten en de GDPR. De Yuki-API-beperkingen en de juridische verwijzingen staan in `docs/DOSSIER-TRANSFER.nl.md` (verifieer de actuele regels).

## 10. Agents
1. Open `agents/README.md` en kies uw platform: Grok Bot, Claude Code-subagent, Claude Desktop-project, GitHub Copilot custom agent of instructies, Cursor-regel (`.mdc`), OpenAI Agents SDK-voorbeeld of een generieke systeemprompt.
2. Er zijn twee profielen: ondernemer (dashboard) en accountant (portfolio). Kopieer het bestand naar de plaats die bovenaan staat (bv. `.claude/agents/` of `.github/agents/`) of plak de instructies.
3. Er wordt niets voor u geïnstalleerd. Menunamen in de platformen wijzigen: verify current docs.

## 11. Postman, integraties en naslag
- **Postman**: importeer `postman/FISCAi-Yuki-API-Connector.postman_collection.json` en het omgevingssjabloon; vul `yuki_access_key` in als geheim; voer eerst `00 Authentication` uit. Het is een aanvullende, alleen-lezen collectie (zie `docs/POSTMAN.nl.md`); de officiële Yuki Postman-documentatie blijft de referentie. Gebruik voor echte gegevens een werkruimte op bestand, niet in de cloud.
- **Integraties**: AgentMail (conceptmails), Hermes Agent en OpenClaw (`docs/integrations/`), visualisatie-, documentgeneratie- en automatiseringstools (`docs/integrations/`).
- **Repository**: CI, labels en rulesets staan in `docs/maintainers/REPO-SETTINGS.md`.

## 12. Optionele boekingsworkflow (standaard uit)
Ze kan journaalposten in Yuki boeken, maar enkel nadat u `YUKI_WRITE_ENABLED=ja` instelt, en dan alleen met een uitdrukkelijke bevestiging per boeking en een auditlog. Workflowdocumenten worden nooit zo geboekt; handel ze af met *Afhandelen* in Yuki. Lees `docs/BOEKINGSWORKFLOW.md` voor u eraan denkt. De meeste gebruikers zetten ze nooit aan.

## 13. Privacy, limieten en hulp
- Gegevens blijven op uw computer; wat de assistent ziet gaat naar de modelaanbieder die u koos (`docs/PRIVACY-DATA-FLOW.md`).
- Daglimiet: standaard 900 per domein; het gratis volume en de regels van Yuki kunnen wijzigen: verifieer de actuele regel. Controleer `yuki_status`.
- Geen fiscaal of juridisch advies: laat cijfers nakijken door uw boekhouder.
- Problemen: `docs/TROUBLESHOOTING.md`; voer `yuki-api-connector doctor` uit.

Powered by FISCALCI Accounting & Tax (Askin Alci)
