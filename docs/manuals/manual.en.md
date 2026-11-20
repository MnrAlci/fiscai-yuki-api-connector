# FISCAi Yuki API Connector: complete manual

> Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

This manual explains every feature and gives step-by-step instructions. The connector is a plugin for Grok Bot (it also works in Copilot, Claude, Cursor, Windsurf and other MCP clients) that reads your Yuki accounting data locally with your own key. It is **read-only for Yuki by default** and is not an official Yuki or Visma product. The official Yuki reference is the [Yuki API Webservices Documentation](https://documenter.getpostman.com/view/12207912/UVCBB51L).

## 1. Install and first run
1. You need Python 3.10 or higher and a Yuki API key (portal key or domain key).
2. Get the code and install the dependencies: `git clone <repository-url> fiscai-yuki-api-connector`, then `cd fiscai-yuki-api-connector`, `python3 -m venv .venv`, `.venv/bin/pip install -r requirements.txt`.
3. Add the folder to Grok Bot as a plugin and fill in `YUKI_ACCESS_KEY` in Grok Bot's own settings. Never put the key in a file, a chat or the repository.
4. Ask Grok Bot: "Run `yuki_status`". This makes no Yuki call and confirms the setup.
5. On the command line: `export YUKI_ACCESS_KEY=...` then `yuki-api-connector doctor`. It checks Python, packages and variables and prints no secrets. Without installing the package use `python3 server/run_connector.py doctor`.

Settings that matter: `YUKI_ACCESS_KEY` (secret), `YUKI_ACCESS_LEVEL` (`portaal` or `domein`), `YUKI_DAILY_LIMIT` (default 900 calls per domain per day), `YUKI_DATA_DIR`. **Never set `YUKI_WRITE_ENABLED`** unless you deliberately want the optional booking workflow (see section 12).

## 2. Use it from an assistant
1. **Grok Bot (recommended)**: install the plugin (section 1) and just ask in plain language: "Give me the ageing of the debtors of [Voorbeeld] BV as of 30/11/2026."
2. **Other MCP clients**: register the server (command, arguments and environment) following the guide in `docs/clients/` for Cursor, Claude Desktop, Claude Code, Copilot (VS Code), Windsurf or a generic client. Use the client's own secret handling for the key.
3. **Agents**: ready-made agent definitions are in `agents/` (section 10).

## 3. The tools, grouped by domain
There are 70 tools (`yuki_*`). Everything is read-only for Yuki except the booking workflow (group "Booking workflow", off by default) and `yuki_opslag_instellen`, which changes a local setting only.

### Status and administrations

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_status` | Daily call counter, limit and access level. Makes no Yuki call. | yes |
| `yuki_administraties` | List the administrations your key can reach. | yes |
| `yuki_administratie_id` | Look up an administration ID by its exact name. | yes |
| `yuki_domeinen` | List the domains reachable with this key. | yes |
| `yuki_bedrijven` | List all available companies (administrations). | yes |
| `yuki_huidig_domein` | Show the current domain of the session. | yes |

### Ledger and balances (read)

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_proefbalans` | Trial balance per ledger account on a date (commercial, fiscal or year-end). | yes |
| `yuki_netto_omzet` | Net revenue for a period. | yes |
| `yuki_openstaande_posten` | Open debtor or creditor items, optionally at a date. | yes |
| `yuki_grootboekmutaties` | Entries on one ledger account in a period. | yes |
| `yuki_rekeningschema` | The chart of accounts. | yes |
| `yuki_boekjaar_gewijzigd` | When a fiscal year was last modified. | yes |
| `yuki_jaartotalen` | Annual totals and ratios (Belgian MAR classes). | yes |
| `yuki_openstaande_posten_periode` | Open items by invoice date range, optionally with payment reference. | yes |
| `yuki_grootboektransacties` | Older Accounting variant of ledger transactions. | yes |
| `yuki_controleer_open_post` | Open amount of one transaction by invoice number or ID. | yes |
| `yuki_startbalans` | Opening balances per ledger account for a fiscal year. | yes |
| `yuki_periodetabel` | Start date of a fiscal year. | yes |
| `yuki_transacties_gepagineerd` | Ledger transactions with paging (all pages by default). | yes |
| `yuki_aangepaste_betaalmethodes` | Custom payment methods. | yes |
| `yuki_rgs_schema` | Chart of accounts with RGS codes (Dutch reference; rarely used in Belgium). | yes |
| `yuki_projecten` | Projects. | yes |
| `yuki_projectsaldo` | Balance of a project per ledger account. | yes |
| `yuki_contact_standaardwaarden` | Default values of a contact in an administration. | yes |
| `yuki_verkoopitems` | Sales items of an administration. | yes |

### Analyses

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_ouderdom_openstaande_posten` | Ageing of open items (not yet due, 0-30, 31-60, 61-90, over 90 days); negative amounts shown separately. | yes |
| `yuki_dso_dpo` | Days sales outstanding and days payables outstanding. | yes |
| `yuki_top_relaties` | Largest open balances per relation. | yes |
| `yuki_periodevergelijking` | Revenue, costs and result versus the previous period or year. | yes |
| `yuki_marge_kostenstructuur` | Gross and net margin and costs per MAR class. | yes |
| `yuki_liquiditeit` | Current ratio, cash ratio, working capital and solvency. | yes |
| `yuki_uitschieters` | Statistical outliers and possible duplicate entries on one account (to be reviewed, no verdict). | yes |
| `yuki_afpuntingsvoorstellen` | Matching proposals for negative open items (proposals only). | yes |

### Dashboards and key figures

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_dashboard` | Dashboard widget with optional static HTML export. | yes |
| `yuki_dashboard_kpis` | Compact key figures of one administration for your own dashboard. | yes |
| `yuki_portfolio_kpis` | Key figures across several administrations (accountant portfolio). | yes |

### Export and dossier transfer

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_export_dataset` | Export kpis, balances or open items to CSV, JSON, xlsx or Parquet. | yes |
| `yuki_dossier_transfer_export` | Per-fiscal-year dossier export for the next accountant, with MANIFEST and CONTROL. | yes |

### Drafts, guidance and local storage

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_herinneringsmail` | Draft reminder e-mail for one relation with open items (never sent). | yes |
| `yuki_handleiding_saldi` | Guidance on positive and negative balances, optionally as .md and .html. | yes |
| `yuki_opslag_status` | Where local outputs are stored. | yes |
| `yuki_opslag_instellen` | Set the local storage location (changes a local setting only). | no (local or gated) |

### VAT

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_btw_aangiftes` | List of VAT returns for a year (read, no filing). | yes |
| `yuki_btw_codes` | Active VAT codes. | yes |

### Archive (documents, metadata only)

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_archief_mappen` | Archive folders. | yes |
| `yuki_archief_mappen_aantallen` | Document counts per folder. | yes |
| `yuki_archief_tabs` | Tabs of an archive folder. | yes |
| `yuki_archief_documenten` | Document metadata, paged (no file contents). | yes |
| `yuki_archief_documenten_in_map` | Document metadata in a folder. | yes |
| `yuki_archief_documenten_in_tab` | Document metadata in a tab. | yes |
| `yuki_archief_documenten_per_type` | Document metadata by document type. | yes |
| `yuki_archief_gewijzigd_per_type` | Modified documents by type. | yes |
| `yuki_archief_gewijzigd_in_map` | Modified documents in a folder. | yes |
| `yuki_archief_zoeken` | Search archive documents. | yes |
| `yuki_archief_document` | Find one document. | yes |
| `yuki_archief_document_xml` | XML data of one document. | yes |
| `yuki_archief_document_paginas` | Number of pages of a document. | yes |
| `yuki_archief_betaalmethodes` | Payment methods (archive). | yes |
| `yuki_archief_kostencategorieen` | Cost categories. | yes |
| `yuki_archief_valuta` | Currencies. | yes |
| `yuki_archief_menu` | Archive menu structure. | yes |
| `yuki_archief_projecten` | Projects (archive). | yes |

### Contacts

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_contacten_zoeken` | Search contacts (paged). | yes |
| `yuki_klanten_leveranciers` | Customers and/or suppliers (paged). | yes |

### Back office and workflow

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_backoffice_workflow` | Back-office workflow items. | yes |
| `yuki_afhandeling_controle` | Check after handling an item in the back office. | yes |

### Booking workflow (OFF by default, writes to Yuki)

| Tool | What it does | Read-only |
|---|---|---|
| `yuki_boeking_voorstel` | Next item and a booking proposal (read; part of the optional booking workflow). | no (local or gated) |
| `yuki_boeking_overslaan` | Skip an item (local state only). | no (local or gated) |
| `yuki_boeking_bevestigen` | Confirm and book a journal entry in Yuki (WRITES; needs YUKI_WRITE_ENABLED and per-entry confirmation). | no (local or gated) |
| `yuki_boeking_status` | Status of the booking workflow. | yes |


## 4. Dashboards and key figures
1. Start with `yuki_dashboard_kpis` (administration, year, optional period `kwartaal:2` or `maand:5`, optional comparison with the previous period): revenue, costs, result, margin, liquid assets, open debtors and creditors (total and overdue), DSO/DPO and a VAT indication.
2. Accountants use `yuki_portfolio_kpis` for several administrations (default 5, maximum 15; about 4 Yuki calls per administration).
3. `yuki_dashboard` shows a widget and can write a static HTML file to a folder you choose.
4. Command line: `yuki-api-connector dashboard --administratie "[Voorbeeld] BV" --jaar 2026 --vergelijk --out kpis.json`. Add `--dry-run` to see the plan without calls.
5. Drill down on request: ageing (`yuki_ouderdom_openstaande_posten`), top relations, margin, liquidity, period comparison, outliers.

## 5. Export layer (CSV, JSON, xlsx, Parquet)
1. Ask Grok Bot to export, or run: `yuki-api-connector export --dataset kpis --administratie "[Voorbeeld] BV" --jaar 2026 --format csv,xlsx --out ./export`. Datasets: `kpis`, `saldi`, `openstaande_posten` (with `--soort debiteuren|crediteuren`).
2. The files have a fixed schema (see `docs/EXPORT-SCHEMA.md`); Parquet needs the optional `pyarrow`.
3. Load the files in your tools: Power BI, Excel, Looker Studio, Metabase, Streamlit and others (guides in `docs/integrations/`). Examples use `[Voorbeeld]` data only.
4. CSV uses UTF-8; Excel in a Belgian locale may ask for the import wizard because of the decimal comma.

## 6. Command line
| Command | Purpose |
|---|---|
| `serve` | start the MCP server (stdio; optional `--http` on localhost only) |
| `doctor [--online]` | check the environment (and one Yuki call with `--online`) |
| `tools [--names-only]` | list the tools |
| `call TOOL --args '{...}'` | call one read-only tool |
| `export`, `dashboard` | exports and key figures (sections 4 and 5) |
| `workflows plan | run | list | init` | automation (section 8) |
| `transfer export` | dossier transfer per fiscal year (section 9) |
| `config init` | write an example `.env` with placeholders |
| `version`, `completion bash|zsh|powershell` | version and shell completion |

Common options: `--json`, `--quiet`, `--verbose`, `--log-level`, `--log-format json`, `--env-file`, `--config` and `--profile`, `--hooks`, `--dry-run`. Settings precedence: command line, then environment, then file; config files never hold secrets. Exit codes: 0 ok, 1 general, 2 usage, 3 configuration, 4 tool/Yuki error, 5 network, 6 refused. Details: `docs/CLI.md`.

## 7. Hooks (optional, off by default)
1. Copy `examples/hooks/hooks.example.toml` and set `enabled = true`.
2. Choose events: `pre_call`, `post_call`, `on_error`, `on_export`, each with a local command (a list, no shell) or a Python function.
3. Start with `--hooks FILE` or set `YUKI_HOOKS_FILE`.
4. Hooks never receive secrets, never break a call, and run with a minimal environment. Examples: copy an export, audit log, webhook, document generator. Details: `docs/HOOKS.md`.

## 8. Automation and reminders
1. `yuki-api-connector workflows init --path workflows.toml` writes an example configuration with `[Voorbeeld]` data.
2. Choose a calendar adapter (ICS file or link, Microsoft Graph, Google Calendar), your clients (match by keyword, e-mail or domain), your overview template and your recurring obligations. Deadlines in the example are **examples marked "verifieer actuele regel"**; check the official source.
3. `workflows list` shows what is configured; `workflows plan` shows what is due (no Yuki calls); `workflows run --dry-run` is the same without writing.
4. `workflows run` writes an overview (Markdown and JSON) per meeting two days ahead (configurable) and per due obligation, lists the missing documents and creates a **draft** reminder e-mail.
5. Mails are never sent by default. Sending needs `allow_send = true`, `--send` and a confirmation per run, and only the SMTP adapter can send. Sending to clients is your own responsibility.
6. Schedule it with cron, Windows Task Scheduler, GitHub Actions (encrypted secrets), n8n, Zapier, Power Automate or a Grok Bot routine. Details and examples: `docs/AUTOMATION.md`.

## 9. Dossier transfer per fiscal year
1. Estimate: `yuki-api-connector transfer export --administration "[Voorbeeld] BV" --fiscal-year 2025 --out ./overdracht --estimate-only`.
2. Run: add one `--fiscal-year` per year (or `--all-years`), optionally `--zip`, `--include-documents` and `--all-accounts`. Above the threshold you confirm with `JA` (or `--yes`).
3. If the daily limit stops the run, repeat the same command later: it resumes from the checkpoint.
4. Read `CONTROL.md` and `MANIFEST.json` in each year folder and the top-level `README.md` written for the receiving accountant.
5. Hand over securely and observe the professional and GDPR points. Yuki API limits and the legal pointers are in `docs/DOSSIER-TRANSFER.md` (verify the current rules).

## 10. Agents
1. Open `agents/README.md` and pick your platform: Grok Bot, Claude Code subagent, Claude Desktop project, GitHub Copilot custom agent or instructions, Cursor rule (`.mdc`), OpenAI Agents SDK example, or a generic system prompt.
2. Two profiles exist: business owner (dashboard) and accountant (portfolio). Copy the file to the place named at its top (for example `.claude/agents/` or `.github/agents/`) or paste the instructions.
3. Nothing is installed for you. Menu names in the platforms change: verify current docs.

## 11. Postman, integrations and reference
- **Postman**: import `postman/FISCAi-Yuki-API-Connector.postman_collection.json` and the environment template; fill `yuki_access_key` as a secret; run `00 Authentication` first. It is a complementary, read-only collection (see `docs/POSTMAN.md`); the official Yuki Postman documentation remains the reference. Use a file-based workspace, not the cloud, for real data.
- **Integrations**: AgentMail (draft mails), Hermes Agent and OpenClaw (`docs/integrations/`), visualisation, document generation and automation tools (`docs/integrations/`).
- **Repository**: CI, labels and rulesets are described in `docs/maintainers/REPO-SETTINGS.md`.

## 12. Optional booking workflow (off by default)
It can book journal entries in Yuki, but only after you set `YUKI_WRITE_ENABLED=ja`, and then only with an explicit confirmation per entry and an audit log. Workflow documents are never booked this way; finish them with *Afhandelen* in Yuki. Read `docs/BOEKINGSWORKFLOW.md` before you consider it. Most users never enable it.

## 13. Privacy, limits and help
- Data stays on your computer; what the assistant sees goes to the model provider you chose (`docs/PRIVACY-DATA-FLOW.md`).
- Daily call limit: default 900 per domain; Yuki's free allowance and rules can change: verify the current rule. Check `yuki_status`.
- Not tax or legal advice: have figures reviewed by your accountant.
- Problems: `docs/TROUBLESHOOTING.md`; run `yuki-api-connector doctor`.

Powered by FISCALCI Accounting & Tax (Askin Alci)
