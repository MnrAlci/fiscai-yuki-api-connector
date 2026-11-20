# Automatisering: vergaderingvoorbereiding en terugkerende verplichtingen

> Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

De module `workflows` bereidt uw werk automatisch voor: **vóór een klantvergadering** (standaard twee dagen vooraf) en **vóór terugkerende verplichtingen** (btw-aangifte, klantenlisting, UBO-register, jaarrekening, vennootschapsbelasting en personenbelasting). Ze maakt een door u bepaald overzicht, toont de **ontbrekende documenten** en kan een **concept** van een herinneringsmail maken. Ze is **alleen-lezen voor Yuki** en **verstuurt standaard niets**.

## Uitgangspunten
- **Yuki: alleen lezen.** Slechts vier leestools zijn toegelaten (`yuki_dashboard_kpis`, `yuki_ouderdom_openstaande_posten`, `yuki_boekjaar_gewijzigd`, `yuki_export_dataset`); al het andere wordt geweigerd. Calls lopen via de [hooks](HOOKS.nl.md) (`pre_call`, `post_call`, `on_error`, `on_export`) als u die aanzette.
- **Concepten, geen mails.** Standaard: een `.eml`-bestand met de header `X-Unsent` (opent als concept in Outlook en de meeste mailprogramma's). Optioneel concepten in Outlook, Gmail of AgentMail.
- **Verzenden is drievoudig vergrendeld**: `[mail] allow_send = true` in de config, `--send` op de opdrachtregel en een bevestiging per run (`--confirm-send`, of `VERSTUUR` typen in een terminal). Alleen de `smtp`-adapter kan versturen. **Verzenden naar klanten is uw eigen verantwoordelijkheid**: controleer tekst, ontvanger en rechtsgrond vóór u het inschakelt.
- **Geen geheimen in de repository of de config.** Tokens komen uit omgevingsvariabelen waarvan u de *naam* in de config zet (`token_env`, `url_env`). De lader weigert sleutels zoals `password`, `token`, `api_key` en `url`.
- **Deadlines zijn in deze code geen feiten.** Ze staan in *uw* config. Het meegeleverde voorbeeld is gemarkeerd als `verifieer actuele regel` en verwijst alleen naar officiële bronnen (FOD Financiën, NBB). Controleer altijd de actuele regel en vervaldatum vóór u erop vertrouwt.
- Gegevens in de voorbeelden zijn uitsluitend `[Voorbeeld]`. De uitvoer bevat klantgegevens: bewaar ze op een beschermde plaats (zie [privacy](PRIVACY-DATA-FLOW.md)).

## Snelstart
```bash
yuki-api-connector workflows init --path workflows.toml      # voorbeeldconfig met [Voorbeeld]-gegevens
yuki-api-connector workflows list -w workflows.toml           # klanten en verplichtingen (met bron en 'verifieer')
yuki-api-connector workflows plan -w workflows.toml           # wat er aankomt; geen Yuki-calls
yuki-api-connector workflows run  -w workflows.toml --dry-run # idem, er wordt niets geschreven
yuki-api-connector workflows run  -w workflows.toml           # overzicht (.md + .json) en concept-.eml per item
```
Zonder installatie van het pakket: `python3 server/run_connector.py workflows ...`. Opties: `--days N` (vergaderingen binnen N dagen, standaard 2), `--today JJJJ-MM-DD`, `--only meetings|obligations`, `--out MAP`, `--force` (afgewerkte items opnieuw), `--json`, `--quiet`. Exitcodes: 0 ok, 3 configuratie, 4 tool-/Yuki-fout, 5 agenda/netwerk, 6 geweigerd (bv. verzenden zonder toestemming).

## 1. Vergaderingvoorbereiding
1. **Agenda-adapter** leest de komende N dagen (`[calendar] adapter`):

| Adapter | Instelling | Opmerkingen |
|---|---|---|
| `ics` | `path` (bestand) of `url_env` (naam van een omgevingsvariabele met een https/webcal-link) | Offline voor bestanden. Privé-ICS-links bevatten een geheim: houd ze in de omgeving. Eenvoudige `RRULE` (dagelijks, wekelijks met `BYDAY`, maandelijks, jaarlijks; `COUNT`, `UNTIL`, `EXDATE`) wordt uitgewerkt; `RDATE`, `BYSETPOS` en gewijzigde afzonderlijke exemplaren niet. |
| `graph` | `token_env` | Microsoft Graph `calendarView` (lezen). Vraagt een gedelegeerd token met `Calendars.Read` dat u zelf verkrijgt. Verify current docs: <https://learn.microsoft.com/graph/api/user-list-calendarview> |
| `google` | `token_env`, `calendar_id` | Google Calendar `events.list` (lezen). Vraagt een token met scope `calendar.readonly`. Verify current docs: <https://developers.google.com/calendar/api/v3/reference/events/list> |

   De plugin voert geen OAuth-flows uit en bewaart geen refresh-tokens; kortlevende tokens zijn uw verantwoordelijkheid (een planner kan er vlak voor de run een ophalen).
2. **Klantherkenning**: een afspraak hoort bij een klant als titel of beschrijving een van de `match_keywords` bevat, een deelnemer/organisator gelijk is aan een `match_emails`, of het domein van een deelnemer in `match_domains` staat. Andere afspraken worden enkel geteld als "niet gekoppeld". Gebruik alleen klantdomeinen, nooit uw eigen.
3. **Overzichtssjabloon** (`[template]`): `sections` (een van `kpis`, `open_items`, `missing_documents`, `dossier_status`, `export`), `kpis` (puntpaden in `yuki_dashboard_kpis`, bv. `open_debiteuren.vervallen`), `compare`, `open_items_kind`, `export_formats`. Een KPI die niet bestaat verschijnt als `n.v.t.`.
4. **Ontbrekende documenten**: vereist = de `documents` van de klant + de `documents` van verplichtingen die nu spelen. Wat ontvangen is komt uit het **statusbestand** van de klant (JSON: `received`, `last_reviewed`, `notes`) dat *u* bijhoudt; zonder dat bestand meldt het overzicht dat niets kon worden nagegaan. De plugin onderzoekt hiervoor het Yuki-archief niet.
5. **Herinneringsconcept** (`[mail]`): gemaakt als er iets ontbreekt. Onderwerp en tekst zijn sjablonen (`[mail.templates.meeting]`, `[mail.templates.obligation]`; plaatshouders `{client}`, `{date}`, `{missing_list}`, `{signature}`, `{context}`, `{deadline}`, `{title}`, `{due}`).

| Mail-adapter | Maakt | Verstuurt |
|---|---|---|
| `eml` (standaard) | `.eml`-concept in `<out>/drafts` | nee |
| `outlook` | concept via Graph `POST /me/messages` (`Mail.ReadWrite`). Verify current docs: <https://learn.microsoft.com/graph/api/user-post-messages> | nee |
| `gmail` | concept via `users.drafts.create` (`gmail.compose`). Verify current docs: <https://developers.google.com/gmail/api/reference/rest/v1/users.drafts/create> | nee |
| `agentmail` | concept in uw AgentMail-inbox (`inbox_env`, `token_env`). Verify current docs: <https://docs.agentmail.to> | nee |
| `smtp` | `.eml`-concept | enkel met de drie sloten (`host_env`, `user_env`, `password_env`, `sender`) |

## 2. Terugkerende verplichtingen
`[[obligations]]` beschrijft een taak: `id`, `title`, `frequency` (`monthly`, `quarterly`, `annual`, `fixed`), de regel (`due_day`, `due_month_offset` voor periodieke; `due_month`, `due_day`, `year_offset` voor jaarlijkse; `dates` voor vaste), `lead_days`, `checklist`, `documents`, `source` (officiële link, verplicht) en `verify`. Een klant kiest met `obligations = ["id", ...]`. Vanaf `lead_days` vóór de vervaldatum tot `overdue_days` erna wordt het item gepland; `run` schrijft het voorbereidingsoverzicht (met checklist) en, bij ontbrekende documenten, een concept om ze te vragen.

De voorbeeldconfig bevat: periodieke btw-aangifte (maand- en kwartaalvariant), jaarlijkse klantenlisting, intracommunautaire listing, UBO-register, jaarrekening (afsluiten en neerleggen), vennootschapsbelasting en personenbelasting. **De getallen daarin zijn voorbeelden, geen regels.** Controleer elk bij de officiële bron vóór gebruik: FOD Financiën <https://financien.belgium.be/nl> en de Nationale Bank van België (Balanscentrale) <https://www.nbb.be/nl/balanscentrale>. Weekends, feestdagen, uitstel en klantspecifieke termijnen worden niet toegepast: zet de gewenste datum in de config.

## 3. Planner
`run` is idempotent: afgewerkte items worden onthouden in `<out>/state.json`, zodat een dagelijkse planning niets herhaalt (`--force` herhaalt wel). Een item met een mislukte sectie wordt bij de volgende run opnieuw geprobeerd. `max_items` (standaard 10) beperkt het aantal items per run, ter bescherming van het Yuki-daglimiet (een KPI-overzicht kost ongeveer 4 Yuki-calls plus 2 voor openstaande posten).

| Waar | Bestand |
|---|---|
| cron (Linux/macOS) | [examples/workflows/cron.txt](../examples/workflows/cron.txt) |
| Windows Taakplanner | [examples/workflows/windows-task-scheduler.ps1](../examples/workflows/windows-task-scheduler.ps1) |
| GitHub Actions schedule | [examples/workflows/github-actions-schedule.yml](../examples/workflows/github-actions-schedule.yml) (niet actief; versleutelde secrets; privé-repository of zelfgehoste runner omdat de uitvoer klantgegevens bevat) |
| n8n | [examples/workflows/n8n-workflow.json](../examples/workflows/n8n-workflow.json) (Schedule Trigger, dan Execute Command) |
| Zapier, Power Automate | Gebruik een geplande flow die de opdracht start op uw eigen machine of server (Zapier: *Schedule by Zapier* plus een code-/webhookstap; Power Automate: *Recurrence* plus een desktopflow of "Run script"). Cloudflows bereiken geen lokaal agendabestand of uw Yuki-sleutel: houd de sleutel op de machine die de opdracht uitvoert. Verify current docs; menunamen wijzigen. |
| Grok Bot-routines | Maak een routine (verify current docs) met een prompt zoals: "Elke werkdag om 07:30 voer `yuki-api-connector workflows run -w <pad> --json` uit, vat de voorbereide items samen en som de concepten op; gebruik nooit `--send`." |

Geheimen: zet `YUKI_ACCESS_KEY` (en een tokenvariabele bij Graph of Google) in de geheimenopslag van de planner of in een omgevingsbestand dat enkel u kunt lezen. Nooit in de config, de crontab-regel, een script of de repository.

## Hooks
Yuki-calls van `workflows` activeren `pre_call`, `post_call` en `on_error`; weggeschreven overzichten activeren `on_export` (`tool = "workflows"`, `files`, `export_dir`) als hooks aanstaan (`--hooks BESTAND` of `YUKI_HOOKS_FILE`; standaard uit, zie [HOOKS.nl.md](HOOKS.nl.md)). Hook-gegevens bevatten nooit geheimen.

## Beperkingen
- Geen fiscale kalender en geen advies: u bepaalt wat wanneer verschuldigd is.
- De klantherkenning is tekstueel; controleer het plan (`workflows plan`) vóór de eerste `run`.
- Ondersteuning van ICS-herhalingen is gedeeltelijk (zie boven). Tijdzones: de ingestelde `timezone` (standaard Europe/Brussels) geldt voor "vandaag" en voor zwevende tijden.
- De adapters voor Graph, Google, Gmail en AgentMail zijn enkel offline getest met nepantwoorden. Verify current docs en test eerst met een wegwerpaccount.

Powered by FISCALCI Accounting & Tax (Askin Alci)
