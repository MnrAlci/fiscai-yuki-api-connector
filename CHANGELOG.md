# Changelog

All notable changes are listed here. The format follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).

## [Unreleased]

### Changed
- `server.json` (MCP Registry) now points to the MCPB bundle attached to the GitHub release v1.0.0 (`registryType` `mcpb`, with `fileSha256`) instead of a PyPI package; there is no PyPI release.

## [1.0.0] - 2026-11-20

### Added
- Repository hygiene: GitHub Actions CI (tests and ruff on a Python matrix), ruff config, pre-commit, Dependabot, CODEOWNERS, PR template, code of conduct, Makefile, optional Dockerfile, ROADMAP, troubleshooting and FAQ, privacy and data-flow page, errors/logging/timeouts page, version-consistency test.
- Dossier transfer per fiscal year: MCP tool `yuki_dossier_transfer_export` and `yuki-api-connector transfer export` (estimate, confirmation above a threshold, resume from a checkpoint, per-year MANIFEST.json with SHA-256, CONTROL.md reconciliations, README for the receiving accountant, optional zip, document metadata with `--include-documents`). Read-only for Yuki; API limits documented ('verifieer actuele regel').
- Complete manuals in English and Dutch (every feature, tools grouped by domain, step-by-step) as Markdown, printable PDF and DOCX in `docs/manuals/`.
- Automation module `yuki-api-connector workflows run|list|plan|init`: meeting preparation (calendar adapters ICS, Microsoft Graph, Google; client detection; user-defined overview template; missing-document list), recurring obligations calendar (Belgian examples marked 'verifieer actuele regel', official sources only), draft reminder e-mails (eml, Outlook, Gmail, AgentMail; sending locked behind config flag, `--send` and per-run confirmation, SMTP only), idempotent state, `max_items` quota guard, hooks integration, scheduler examples (cron, Task Scheduler, GitHub Actions, n8n), EN/NL docs. Read-only for Yuki.
- Architecture diagram: new 'Automation & reminders' box (re-upload `docs/images/architecture.png`).
- Postman collection v2.1 (63 read requests per Yuki service, SOAP envelopes from the plugin's own client, disabled folder for write calls) with an environment template and EN/NL guides. File-based, complementary to the official Yuki Postman documentation; not an official product.
- Command line `yuki-api-connector` (serve, doctor, tools, call, export, dashboard, config init, version, completion) with `--json`, `--dry-run`, log options, profiles, exit codes; opt-in hooks (pre_call, post_call, on_error, on_export; off by default, no secrets) with examples; opt-in retry with backoff (`YUKI_MAX_RETRIES`); dev container.
- `agents/`: shared core instructions and two profiles (business owner, accountant) as ready-made files for Grok Bot, Claude Code and Desktop, GitHub Copilot, Cursor, OpenAI Agents SDK (Python example) and open models; root `AGENTS.md`.
- 70 tools for Yuki (Visma), read-only by default: administrations, balances, ledger entries, open items, VAT returns, contacts, archive metadata, backoffice workflow.
- Analyses: ageing, DSO/DPO, top relations, period comparison, margin and cost structure, liquidity ratios, ledger outliers.
- Dashboard (MCP app widget and HTML export), draft reminder emails (never sent), guide on positive and negative balances, matching proposals, storage choice per administration.
- Access level portal or domain; daily call limit (default 900, free up to 1000, above with confirmation and warning).
- Optional booking workflow (off by default): one confirmed journal entry at a time, one-time token, double-entry check, reason required for 0% VAT, daily maximum, audit log.
- Back-office check `yuki_afhandeling_controle` for workflow documents finished with the **Afhandelen** button in Yuki.

- Two read-only tools: `yuki_dashboard_kpis` (compact key figures for one administration) and `yuki_portfolio_kpis` (key figures across several administrations, error per file isolated).
- Read-only export `yuki_export_dataset` with a fixed schema (`kpis`, `saldi`, `openstaande_posten`) to CSV, JSON, xlsx and Parquet (optional `pyarrow`); see `docs/EXPORT-SCHEMA.md`.
- Client guides (Grok Bot first, then Cursor, Claude Desktop, Claude Code, GitHub Copilot in VS Code, Windsurf, generic), integration guides (AgentMail, Hermes Agent, OpenClaw), visualisation and data-app guides (13 tools, two runnable examples), 10 document generators with example templates, data collection and automation guides, and an overview of 40 useful apps.
- Business owner and accountant guides (EN/NL) with illustrations, two skills, `examples/` with placeholder-only configs, `pyproject.toml` with the console command `yuki-api-connector`.

### Added (marketplace readiness)
- `server.json` for the official MCP Registry (`io.github.MnrAlci/fiscai-yuki-api-connector`, PyPI package, stdio).
- `glama.json` (maintainer claim) and `.claude-plugin/plugin.json` (Claude plugin directory; key stored as a sensitive user setting).
- Console command `fiscai-yuki-api-connector` so `uvx fiscai-yuki-api-connector` starts the MCP server.
- PyPI metadata: SPDX licence with LICENSE and NOTICE in the wheel, project URLs, keywords, classifiers.

### Safety
- Workflow documents (purchase and sales) are refused as journal entries; they are finished in Yuki.
- Write methods other than `Accounting.ProcessJournal` are always refused; keys never appear in files, logs or output.

### Documentation
- Positioned as a plugin for Grok Bot (recommended install), with notes for other MCP clients.
- English README with architecture diagram and example output, Dutch README, `docs/` index, tool list and booking workflow guide.

### Fixed
- Element order of the SOAP requests for the period-based outstanding-item methods (`OutstandingDebtorItemsByDate`, `OutstandingCreditorItemsByDate`, `Outstanding{Debtor|Creditor}WithPaymentReference`) and `GetSuppliersAndCustomers` now follows the public WSDL (found by cross-checking the official Yuki Postman documentation); the Postman collection follows the same order.
- Unfilled `${YUKI_...}` placeholders from MCP clients that do not substitute variables are now treated as "not set" instead of stopping the server at startup.
- Cursor plugin manifest lists its agents, rules, skills and MCP server explicitly (with `${CURSOR_PLUGIN_ROOT}`), so the helper files in `agents/` are no longer picked up as agents.
- Attribution line on the docs index, tool list, booking workflow and read-method inventory; Belgium notice on the docs index.
- Removed an internal-edition office rule from the public skill.
