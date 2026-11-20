# Command line (`yuki-api-connector`)

> Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.
>
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

The CLI wraps the same read-only tools as the MCP server. It never writes to Yuki: `call` refuses every tool that is not marked read-only (and the booking tools).

## Install and run
```bash
python3 -m venv .venv && .venv/bin/pip install .      # installs the command `yuki-api-connector`
# or without installing:  python3 server/run_connector.py <command>
yuki-api-connector --help
```

## Commands
| Command | What it does |
|---|---|
| `serve` | Start the MCP server on stdio (what MCP clients launch). `serve --http [--port 8765]` offers a minimal JSON-RPC endpoint on **localhost only** (127.0.0.1; Host and Origin are checked; no authentication, no SSE; verify current MCP client docs before relying on it). |
| `doctor [--online]` | Checks Python, dependencies, environment variables, hooks and data folder. Never prints secrets. `--online` makes one Yuki call to test connectivity. |
| `tools [--names-only]` | Lists the tools with descriptions. |
| `call TOOL --args JSON` | Calls one read-only tool. `--args @file.json` reads the JSON from a file. |
| `export --dataset kpis\|saldi\|openstaande_posten --administratie NAME --jaar 2026 --format csv,json --out DIR` | Writes the dataset (CSV, JSON, xlsx, Parquet). |
| `dashboard --administratie NAME --jaar 2026 [--vergelijk] [--out kpis.json]` | Key figures in the terminal or as a JSON file. |
| `config init [--path .env]` | Writes an example `.env` with placeholders (file mode 0600). |
| `version` | Prints the version. |
| `completion bash\|zsh\|powershell` | Prints a shell completion script (for example `eval "$(yuki-api-connector completion bash)"`). |

## Global options (before or after the command)
`--json` (machine-readable output), `-q/--quiet`, `-v/--verbose`, `--log-level debug|info|warning|error|critical`, `--log-format text|json`, `--env-file FILE`, `--config FILE`, `--profile NAME`, `--hooks FILE`, `--dry-run`, `--access-level portaal|domein`, `--data-dir DIR`.

## Exit codes
| Code | Meaning |
|---|---|
| 0 | OK |
| 1 | General error |
| 2 | Usage error (bad option, missing or unknown parameter) |
| 3 | Configuration or environment problem (for example no key, bad config file) |
| 4 | Tool or Yuki error |
| 5 | Network problem (`doctor --online`) |
| 6 | Refused (tool is not read-only, or `--http` on a non-local host) |

## Configuration precedence
**CLI options > environment variables > files** (`--env-file`, `--config`). A file never overrides a variable that is already set. Secrets (the Yuki key) belong in the environment or a `.env` outside version control, never in the config file: a config file with a key-like setting is rejected.

## Profiles (several administrations or keys)
```toml
# yuki.toml: no secrets
[default]
access_level = "portaal"
max_retries = 1

[profiles.klant_a]
access_level = "domein"
key_env = "YUKI_ACCESS_KEY_KLANT_A"   # the NAME of the variable that holds the key
```
`yuki-api-connector --config yuki.toml --profile klant_a doctor`. Allowed settings: `access_level, daily_limit, daily_warn, data_dir, response_cache, max_retries, log_level, log_format, hooks_file, key_env, administratie`. TOML needs Python 3.11+ (or the `tomli` package); a `.json` file works everywhere.

## Dry run
`--dry-run` validates the tool and parameters and prints what would happen; it makes no Yuki calls.

## Caching, rate limit, retry, pagination
- **Cache:** read responses are cached locally with a TTL (24 h for closed periods and master data, 1 h for the open period); `"vernieuwen": true` in the tool arguments forces a refresh; `YUKI_RESPONSE_CACHE=off` disables it.
- **Rate limit:** hard daily call limit (default 900 per domain, warning at 720); see [OPERATIONS.md](OPERATIONS.md).
- **Retry:** opt-in, off by default: `YUKI_MAX_RETRIES=2` retries *network errors only* (never Yuki faults, never writes) with exponential backoff and jitter, at most 5.
- **Pagination and date ranges:** tools that page (archive, transactions) accept `paginagrootte` and `start`; period tools accept `jaar` plus `periode` (`jaar`, `kwartaal:n`, `maand:n`) and `peildatum`; `call --args` passes them through.

## Structured logging
`--log-format json` (or `YUKI_LOG_FORMAT=json`) writes JSON lines to **stderr** (stdout stays clean for MCP and `--json`). Messages pass the secret scrubber; tool arguments are never logged.

## Docker and dev container
`Dockerfile` runs `serve` as a non-root user: `docker run -i --rm -e YUKI_ACCESS_KEY fiscai-yuki-api-connector` (not tested in CI). `.devcontainer/devcontainer.json` gives VS Code / Codespaces a ready Python 3.12 environment (verify current dev container docs).

## Examples
```bash
yuki-api-connector doctor
yuki-api-connector tools --names-only
yuki-api-connector call yuki_administraties --json
yuki-api-connector export --dataset kpis --administratie "[Voorbeeld] BV" --jaar 2026 --format csv,xlsx --out ./export
yuki-api-connector dashboard --administratie "[Voorbeeld] BV" --jaar 2026 --vergelijk --out kpis.json
```
CSV files use a dot as decimal separator and UTF-8; Excel in a Belgian locale may need the import wizard (Data, From text/CSV) to read them correctly.


## Automation and dossier transfer

| Command | Purpose |
|---|---|
| `workflows init --path workflows.toml` | write an example configuration (`[Voorbeeld]` data) |
| `workflows list` / `plan` / `run` | list, plan (no Yuki calls) or run meeting preparation and recurring obligations; drafts only, see [AUTOMATION.md](AUTOMATION.md) |
| `transfer export --administration X --fiscal-year YYYY --out DIR [--zip] [--include-documents]` | dossier export per fiscal year; see [DOSSIER-TRANSFER.md](DOSSIER-TRANSFER.md) |

Exit code 6 means a required confirmation was missing (send or transfer above the threshold).
