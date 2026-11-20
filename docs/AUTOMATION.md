# Automation: meeting preparation and recurring obligations

> Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

The `workflows` module prepares your work automatically: **before a client meeting** (default two days ahead) and **before recurring obligations** (VAT return, client listing, UBO register, annual accounts, corporate and personal income tax). It builds an overview you define, lists the **missing documents** and can create a **draft** reminder e-mail. It is **read-only for Yuki** and **never sends anything by default**.

## Principles
- **Yuki: read-only.** Only four read tools are allowed (`yuki_dashboard_kpis`, `yuki_ouderdom_openstaande_posten`, `yuki_boekjaar_gewijzigd`, `yuki_export_dataset`); anything else is refused. Calls go through the [hooks](HOOKS.md) (`pre_call`, `post_call`, `on_error`, `on_export`) when you enabled them.
- **Drafts, not mails.** Default: an `.eml` file with the `X-Unsent` header (opens as a draft in Outlook and most mail apps). Optional drafts in Outlook, Gmail or AgentMail.
- **Sending is locked three times**: `[mail] allow_send = true` in the config, `--send` on the command line and a confirmation per run (`--confirm-send`, or typing `VERSTUUR` in a terminal). Only the `smtp` adapter can send. **Sending to clients is your own responsibility**: check the text, the recipient and the legal basis before you enable it.
- **No secrets in the repository or the config.** Tokens come from environment variables whose *name* you put in the config (`token_env`, `url_env`). The loader rejects keys such as `password`, `token`, `api_key` and `url`.
- **Deadlines are not facts in this code.** They live in *your* config. The shipped example is marked `verifieer actuele regel` (verify the current rule) and links only to official sources (FOD Financiën, NBB). Always check the current rule and deadline before you rely on it.
- Data in the examples is `[Voorbeeld]` only. Output contains client data: store it in a protected location (see [privacy](PRIVACY-DATA-FLOW.md)).

## Quick start
```bash
yuki-api-connector workflows init --path workflows.toml      # example config with [Voorbeeld] data
yuki-api-connector workflows list -w workflows.toml           # clients and obligations (with source and 'verify')
yuki-api-connector workflows plan -w workflows.toml           # what is due; no Yuki calls
yuki-api-connector workflows run  -w workflows.toml --dry-run # same, nothing written
yuki-api-connector workflows run  -w workflows.toml           # overview (.md + .json) and draft .eml per item
```
Without installing the package: `python3 server/run_connector.py workflows ...`. Options: `--days N` (meetings within N days, default 2), `--today YYYY-MM-DD`, `--only meetings|obligations`, `--out DIR`, `--force` (redo finished items), `--json`, `--quiet`. Exit codes: 0 ok, 3 configuration, 4 tool/Yuki error, 5 calendar/network, 6 refused (for example sending without permission).

## 1. Meeting preparation
1. **Calendar adapter** reads the next N days (`[calendar] adapter`):

| Adapter | Setting | Notes |
|---|---|---|
| `ics` | `path` (file) or `url_env` (name of an environment variable holding an https/webcal link) | Offline for files. Private ICS links contain a secret: keep them in the environment. Simple `RRULE` (daily, weekly with `BYDAY`, monthly, yearly; `COUNT`, `UNTIL`, `EXDATE`) is expanded; `RDATE`, `BYSETPOS` and edited single occurrences are not. |
| `graph` | `token_env` | Microsoft Graph `calendarView` (read). Needs a delegated token with `Calendars.Read` that you obtain yourself. Verify current docs: <https://learn.microsoft.com/graph/api/user-list-calendarview> |
| `google` | `token_env`, `calendar_id` | Google Calendar `events.list` (read). Needs a token with the `calendar.readonly` scope. Verify current docs: <https://developers.google.com/calendar/api/v3/reference/events/list> |

   The plugin does not run OAuth flows and stores no refresh tokens; short-lived tokens are your responsibility (a scheduler can fetch one just before the run).
2. **Client detection**: an event belongs to a client when the title or description contains one of `match_keywords`, an attendee/organiser equals one of `match_emails`, or the attendee's domain is in `match_domains`. Other events are only counted as "not linked". Use client domains only, never your own.
3. **Overview template** (`[template]`): `sections` (any of `kpis`, `open_items`, `missing_documents`, `dossier_status`, `export`), `kpis` (dotted paths into `yuki_dashboard_kpis`, for example `open_debiteuren.vervallen`), `compare`, `open_items_kind`, `export_formats`. A KPI that does not exist is shown as `n.v.t.`.
4. **Missing documents**: required = the client's `documents` + the `documents` of obligations that are currently due. What was received comes from the client's **status file** (JSON: `received`, `last_reviewed`, `notes`) that *you* maintain; without it the overview says that nothing could be checked. The plugin does not inspect the Yuki archive for this.
5. **Reminder draft** (`[mail]`): created when something is missing. Subject and body are templates (`[mail.templates.meeting]`, `[mail.templates.obligation]`; placeholders `{client}`, `{date}`, `{missing_list}`, `{signature}`, `{context}`, `{deadline}`, `{title}`, `{due}`).

| Mail adapter | Creates | Sends |
|---|---|---|
| `eml` (default) | `.eml` draft in `<out>/drafts` | no |
| `outlook` | draft via Graph `POST /me/messages` (`Mail.ReadWrite`). Verify current docs: <https://learn.microsoft.com/graph/api/user-post-messages> | no |
| `gmail` | draft via `users.drafts.create` (`gmail.compose`). Verify current docs: <https://developers.google.com/gmail/api/reference/rest/v1/users.drafts/create> | no |
| `agentmail` | draft in your AgentMail inbox (`inbox_env`, `token_env`). Verify current docs: <https://docs.agentmail.to> | no |
| `smtp` | `.eml` draft | only with the three locks (`host_env`, `user_env`, `password_env`, `sender`) |

## 2. Recurring obligations
`[[obligations]]` describes a task: `id`, `title`, `frequency` (`monthly`, `quarterly`, `annual`, `fixed`), the rule (`due_day`, `due_month_offset` for periodic ones; `due_month`, `due_day`, `year_offset` for annual ones; `dates` for fixed ones), `lead_days`, `checklist`, `documents`, `source` (official link, required) and `verify`. A client opts in with `obligations = ["id", ...]`. From `lead_days` before the due date until `overdue_days` after it, the item is planned; `run` writes the prep overview (with checklist) and, if documents are missing, a draft asking for them.

The example config contains: periodic VAT return (monthly and quarterly variants), annual client listing, intra-Community listing, UBO register check, annual accounts (closing and filing), corporate tax and personal income tax. **The numbers in it are examples, not rules.** Check each with the official source before you use it: FOD Financiën <https://financien.belgium.be/nl> and the National Bank of Belgium (Balanscentrale) <https://www.nbb.be/nl/balanscentrale>. Weekends, holidays, extensions and client-specific deadlines are not applied: put the date you want in the config.

## 3. Scheduler
`run` is idempotent: finished items are remembered in `<out>/state.json`, so a daily schedule does not repeat work (`--force` repeats). An item with a failed section is retried at the next run. `max_items` (default 10) limits how many items one run processes, to protect the Yuki daily limit (a KPI overview costs roughly 4 Yuki calls plus 2 for open items).

| Where | File |
|---|---|
| cron (Linux/macOS) | [examples/workflows/cron.txt](../examples/workflows/cron.txt) |
| Windows Task Scheduler | [examples/workflows/windows-task-scheduler.ps1](../examples/workflows/windows-task-scheduler.ps1) |
| GitHub Actions schedule | [examples/workflows/github-actions-schedule.yml](../examples/workflows/github-actions-schedule.yml) (not active; encrypted secrets; private repository or self-hosted runner because output contains client data) |
| n8n | [examples/workflows/n8n-workflow.json](../examples/workflows/n8n-workflow.json) (Schedule Trigger, then Execute Command) |
| Zapier, Power Automate | Use a scheduled flow that starts the command on your own machine or server (Zapier: *Schedule by Zapier* plus a code/webhook step; Power Automate: *Recurrence* plus a desktop-flow or "Run script" action). Cloud flows cannot reach a local calendar file or your Yuki key: keep the key on the machine that runs the command. Verify current docs; menu names change. |
| Grok Bot routines | Create a routine (verify current docs) with a prompt such as: "Every weekday at 07:30 run `yuki-api-connector workflows run -w <path> --json`, summarise the prepared items and list the drafts; never use `--send`." |

Secrets: put `YUKI_ACCESS_KEY` (and a token variable if you use Graph or Google) in the scheduler's secret store or an environment file readable only by you. Never in the config, the crontab line, a script or the repository.

## Hooks
Yuki calls made by `workflows` fire `pre_call`, `post_call` and `on_error`; written overviews fire `on_export` (`tool = "workflows"`, `files`, `export_dir`) when hooks are enabled (`--hooks FILE` or `YUKI_HOOKS_FILE`; off by default, see [HOOKS.md](HOOKS.md)). Hook payloads never contain secrets.

## Limits
- Not a tax calendar and not advice: you decide what is due and when.
- The client match is textual; check the plan (`workflows plan`) before the first `run`.
- ICS recurrence support is partial (see above). Time zones: the configured `timezone` (default Europe/Brussels) is used for "today" and for floating times.
- Graph, Google, Gmail and AgentMail adapters are tested offline with fake responses only. Verify current docs and test with a throw-away account first.

Powered by FISCALCI Accounting & Tax (Askin Alci)
