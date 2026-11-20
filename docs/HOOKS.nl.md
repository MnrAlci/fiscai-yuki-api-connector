# Hooks (haken)

> Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

Met hooks voert u een eigen lokaal script of Python-functie uit rond toolaanroepen. Ze staan **standaard uit**, draaien enkel op uw machine en **krijgen nooit geheimen**.

## Inschakelen
Verwijs naar een hooks-bestand met `--hooks hooks.toml` of `YUKI_HOOKS_FILE=hooks.toml` **en** zet `enabled = true` erin. Zonder beide gebeurt er niets.

```toml
enabled = true
timeout_seconds = 10

[[hooks]]
event = "on_export"
name = "copy export"
command = ["python3", "examples/hooks/copy_export.py"]     # een lijst, nooit een shelltekst

[[hooks]]
event = "post_call"
python = "my_hooks:notify"                                 # module:functie, gezocht naast het hooks-bestand
tools = ["yuki_dashboard_kpis"]                            # optioneel filter
```
JSON werkt ook (`hooks.json`). TOML vraagt Python 3.11+ of `tomli`.

## Events
| Event | Wanneer | Payload (JSON op stdin / dict) |
|---|---|---|
| `pre_call` | voor een toolaanroep | `event, time, tool, args` |
| `post_call` | na een geslaagde aanroep | `+ ok, duration_ms, result_summary` (enkel sleutels en grootte, niet de data) |
| `on_error` | na een mislukte aanroep | `+ error` (gescrubd), `duration_ms` |
| `on_export` | nadat `yuki_export_dataset` bestanden schreef | `+ files, export_dir` |

## Veiligheid
- Argumenten gaan door een filter: sleutels als `key`, `token`, `secret`, `password`, `authorization` worden `[verborgen]` en tekst wordt gescrubd. Tool-**resultaten** worden niet doorgegeven, enkel een samenvatting.
- Commandohooks draaien zonder shell, in de map van het hooks-bestand, met een minimale omgeving (`PATH`, `HOME`, taal, tijdelijke map) plus `YUKI_HOOK_EVENT` en `YUKI_HOOK_TOOL`. Er worden geen `YUKI_*`-geheimen doorgegeven.
- Een hook die faalt of een time-out krijgt wordt gelogd en genegeerd; ze breekt de toolaanroep nooit. Hooks kunnen argumenten of resultaten niet wijzigen.
- Hooks voeren code uit die u zelf schreef: verwijs enkel naar bestanden die u vertrouwt. Exportbestanden kunnen klantgegevens bevatten; stuur ze niet naar diensten waarmee u geen overeenkomst hebt.

## Voorbeelden (`examples/hooks/`)
- `hooks.example.toml`: de drie hooks hierboven.
- `copy_export.py`: kopieert geëxporteerde bestanden naar een andere lokale map (bv. een gesynchroniseerde map).
- `webhook_notify.py`: post een korte melding (tool, event, aantal bestanden; geen data) naar de URL in `YUKI_HOOK_WEBHOOK_URL`. Enkel een plaatshouder: stel ze zelf in en let op: dit doet een netwerkaanroep naar die URL.
- `run_document_generator.py`: start een documentgenerator na een export (zie [docs/integrations/documenten](integrations/documenten/README.md)).

## Hooks aan clientzijde (verifieer actuele documentatie)
Deze horen bij uw AI-client of git, niet bij deze plugin.

**Claude Code hooks** (`.claude/settings.json`; verifieer actuele documentatie: https://docs.claude.com/en/docs/claude-code/hooks):
```json
{"hooks": {"PreToolUse": [{"matcher": "mcp__fiscai-yuki-api-connector__.*", "hooks": [{"type": "command", "command": "python3 examples/hooks/audit_log.py"}]}]}}
```
**Cursor hooks** (`.cursor/hooks.json`; het formaat verschilde tussen versies: verifieer actuele documentatie: https://cursor.com/docs/agent/hooks):
```json
{"version": 1, "hooks": {"beforeMCPExecution": [{"command": "python3 examples/hooks/audit_log.py"}]}}
```
**git pre-commit** (deze repository bevat `.pre-commit-config.yaml`; verifieer actuele documentatie: https://pre-commit.com): voeg een lokale hook toe die gestagede bestanden met sleutel-achtige patronen weigert:
```yaml
- repo: local
  hooks:
    - id: no-yuki-secrets
      name: no secrets
      entry: python3 examples/hooks/check_no_secrets.py
      language: system
```
`audit_log.py` and `check_no_secrets.py` staan in `examples/hooks/`; ze lezen het JSON-event of de bestandslijst en tonen nooit geheimen.
