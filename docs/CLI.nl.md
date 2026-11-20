# Opdrachtregel (`yuki-api-connector`)

> Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.
>
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

De CLI gebruikt dezelfde alleen-lezen tools als de MCP-server. Er wordt nooit in Yuki geschreven: `call` weigert elke tool die niet als alleen-lezen is gemarkeerd (en de boekingstools).

## Installeren en starten
```bash
python3 -m venv .venv && .venv/bin/pip install .      # installeert het commando `yuki-api-connector`
# of zonder installatie:  python3 server/run_connector.py <opdracht>
yuki-api-connector --help
```

## Opdrachten
| Opdracht | Wat het doet |
|---|---|
| `serve` | Start de MCP-server op stdio (wat MCP-clients opstarten). `serve --http [--port 8765]` biedt een minimaal JSON-RPC-eindpunt **alleen op localhost** (127.0.0.1; Host en Origin worden gecontroleerd; geen authenticatie, geen SSE; verifieer de actuele MCP-clientdocumentatie). |
| `doctor [--online]` | Controleert Python, afhankelijkheden, omgevingsvariabelen, hooks en datamap. Toont nooit geheimen. `--online` doet één Yuki-call om de verbinding te testen. |
| `tools [--names-only]` | Toont de tools met omschrijving. |
| `call TOOL --args JSON` | Roept één alleen-lezen tool aan. `--args @bestand.json` leest de JSON uit een bestand. |
| `export --dataset kpis\|saldi\|openstaande_posten --administratie NAAM --jaar 2026 --format csv,json --out MAP` | Schrijft de dataset (CSV, JSON, xlsx, Parquet). |
| `dashboard --administratie NAAM --jaar 2026 [--vergelijk] [--out kpis.json]` | Kerncijfers in de terminal of als JSON-bestand. |
| `config init [--path .env]` | Schrijft een voorbeeld-`.env` met plaatshouders (bestandsmodus 0600). |
| `version` | Toont de versie. |
| `completion bash\|zsh\|powershell` | Toont een aanvullingsscript (bv. `eval "$(yuki-api-connector completion bash)"`). |

## Globale opties (voor of na de opdracht)
`--json`, `-q/--quiet`, `-v/--verbose`, `--log-level`, `--log-format text|json`, `--env-file BESTAND`, `--config BESTAND`, `--profile NAAM`, `--hooks BESTAND`, `--dry-run`, `--access-level portaal|domein`, `--data-dir MAP`.

## Exitcodes
| Code | Betekenis |
|---|---|
| 0 | OK |
| 1 | Algemene fout |
| 2 | Gebruiksfout (verkeerde optie, ontbrekende of onbekende parameter) |
| 3 | Configuratie- of omgevingsprobleem (bv. geen sleutel, ongeldig configbestand) |
| 4 | Tool- of Yuki-fout |
| 5 | Netwerkprobleem (`doctor --online`) |
| 6 | Geweigerd (tool is niet alleen-lezen, of `--http` op een niet-lokale host) |

## Voorrang van instellingen
**CLI-opties > omgevingsvariabelen > bestanden** (`--env-file`, `--config`). Een bestand overschrijft nooit een variabele die al is ingesteld. Geheimen (de Yuki-sleutel) horen in de omgeving of in een `.env` buiten versiebeheer, nooit in het configbestand: een configbestand met een sleutel-achtige instelling wordt geweigerd.

## Profielen (meerdere administraties of sleutels)
```toml
# yuki.toml: geen geheimen
[default]
access_level = "portaal"
max_retries = 1

[profiles.klant_a]
access_level = "domein"
key_env = "YUKI_ACCESS_KEY_KLANT_A"   # de NAAM van de variabele met de sleutel
```
`yuki-api-connector --config yuki.toml --profile klant_a doctor`. Toegelaten instellingen: `access_level, daily_limit, daily_warn, data_dir, response_cache, max_retries, log_level, log_format, hooks_file, key_env, administratie`. TOML vraagt Python 3.11+ (of het pakket `tomli`); een `.json`-bestand werkt overal.

## Dry run
`--dry-run` valideert tool en parameters en toont wat er zou gebeuren; er zijn geen Yuki-calls.

## Cache, limiet, retry, paginering
- **Cache:** leesantwoorden worden lokaal gecachet met een TTL (24 u voor afgesloten periodes en stamgegevens, 1 u voor de lopende periode); `"vernieuwen": true` in de toolargumenten forceert verversen; `YUKI_RESPONSE_CACHE=off` zet de cache uit.
- **Limiet:** harde daglimiet (standaard 900 per domein, waarschuwing bij 720); zie [OPERATIONS.md](OPERATIONS.md).
- **Retry:** opt-in, standaard uit: `YUKI_MAX_RETRIES=2` herhaalt *enkel netwerkfouten* (nooit Yuki-fouten, nooit schrijfacties) met exponentiële backoff en jitter, maximaal 5.
- **Paginering en datumbereik:** pagineerbare tools (archief, transacties) kennen `paginagrootte` en `start`; periodetools kennen `jaar` plus `periode` (`jaar`, `kwartaal:n`, `maand:n`) en `peildatum`; `call --args` geeft ze door.

## Gestructureerde logging
`--log-format json` (of `YUKI_LOG_FORMAT=json`) schrijft JSON-regels naar **stderr** (stdout blijft schoon voor MCP en `--json`). Berichten gaan door de geheimen-scrubber; toolargumenten worden nooit gelogd.

## Docker en dev container
De `Dockerfile` draait `serve` als niet-root gebruiker: `docker run -i --rm -e YUKI_ACCESS_KEY fiscai-yuki-api-connector` (niet getest in CI). `.devcontainer/devcontainer.json` geeft VS Code / Codespaces een Python 3.12-omgeving (verifieer de actuele dev container-documentatie).

## Voorbeelden
```bash
yuki-api-connector doctor
yuki-api-connector tools --names-only
yuki-api-connector call yuki_administraties --json
yuki-api-connector export --dataset kpis --administratie "[Voorbeeld] BV" --jaar 2026 --format csv,xlsx --out ./export
yuki-api-connector dashboard --administratie "[Voorbeeld] BV" --jaar 2026 --vergelijk --out kpis.json
```
CSV-bestanden gebruiken een punt als decimaalteken en UTF-8; Excel met Belgische instellingen heeft soms de importwizard nodig (Gegevens, Uit tekst/CSV).


## Automatisering en dossieroverdracht

| Opdracht | Doel |
|---|---|
| `workflows init --path workflows.toml` | schrijf een voorbeeldconfiguratie (`[Voorbeeld]`-gegevens) |
| `workflows list` / `plan` / `run` | lijst, plan (zonder Yuki-calls) of uitvoering van vergaderingsvoorbereiding en terugkerende verplichtingen; enkel concepten, zie [AUTOMATION.nl.md](AUTOMATION.nl.md) |
| `transfer export --administration X --fiscal-year JJJJ --out MAP [--zip] [--include-documents]` | dossierexport per boekjaar; zie [DOSSIER-TRANSFER.nl.md](DOSSIER-TRANSFER.nl.md) |

Exitcode 6 betekent dat een vereiste bevestiging ontbrak (verzenden of overdracht boven de drempel).
