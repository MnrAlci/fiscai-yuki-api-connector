# Hooks

> Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

Hooks let you run your own local script or Python function around tool calls. They are **off by default**, run only on your machine, and **never receive secrets**.

## Enable
Point to a hooks file with `--hooks hooks.toml` or `YUKI_HOOKS_FILE=hooks.toml` **and** set `enabled = true` in it. Without both, nothing runs.

```toml
enabled = true
timeout_seconds = 10

[[hooks]]
event = "on_export"
name = "copy export"
command = ["python3", "examples/hooks/copy_export.py"]     # a list, never a shell string

[[hooks]]
event = "post_call"
python = "my_hooks:notify"                                 # module:function, looked up next to the hooks file
tools = ["yuki_dashboard_kpis"]                            # optional filter
```
JSON works too (`hooks.json`). TOML needs Python 3.11+ or `tomli`.

## Events
| Event | When | Payload (JSON on stdin / dict) |
|---|---|---|
| `pre_call` | before a tool call | `event, time, tool, args` |
| `post_call` | after a successful call | `+ ok, duration_ms, result_summary` (keys and size only, not the data) |
| `on_error` | after a failed call | `+ error` (scrubbed), `duration_ms` |
| `on_export` | after `yuki_export_dataset` wrote files | `+ files, export_dir` |

## Safety
- Arguments pass a sanitiser: keys such as `key`, `token`, `secret`, `password`, `authorization` are replaced by `[verborgen]`, and strings are scrubbed. Tool **results** are not passed, only a summary.
- Command hooks run without a shell, in the hooks file's folder, with a minimal environment (`PATH`, `HOME`, locale, temp folder) plus `YUKI_HOOK_EVENT` and `YUKI_HOOK_TOOL`. No `YUKI_*` secrets are passed on.
- A hook that fails or times out is logged and ignored; it never breaks the tool call. Hooks cannot change arguments or results.
- Hooks run arbitrary code you wrote: only point to files you trust. Export files can contain client data; do not send them to services you have no agreement with.

## Examples (`examples/hooks/`)
- `hooks.example.toml`: the three hooks below.
- `copy_export.py`: copies exported files to another local folder (for example a synced folder).
- `webhook_notify.py`: posts a short notice (tool, event, number of files; no data) to the URL in `YUKI_HOOK_WEBHOOK_URL`. Placeholder only: set it yourself, and note it makes a network call to that URL.
- `run_document_generator.py`: starts a document generator command after an export (see [docs/integrations/documenten](integrations/documenten/README.md)).

## Client-side hooks (verify current docs)
These belong to your AI client or git, not to this plugin.

**Claude Code hooks** (`.claude/settings.json`; verify current docs: https://docs.claude.com/en/docs/claude-code/hooks):
```json
{"hooks": {"PreToolUse": [{"matcher": "mcp__fiscai-yuki-api-connector__.*", "hooks": [{"type": "command", "command": "python3 examples/hooks/audit_log.py"}]}]}}
```
**Cursor hooks** (`.cursor/hooks.json`; the format has changed between versions: verify current docs: https://cursor.com/docs/agent/hooks):
```json
{"version": 1, "hooks": {"beforeMCPExecution": [{"command": "python3 examples/hooks/audit_log.py"}]}}
```
**git pre-commit** (this repository ships `.pre-commit-config.yaml`; verify current docs: https://pre-commit.com): add a local hook that rejects staged files matching key-like patterns:
```yaml
- repo: local
  hooks:
    - id: no-yuki-secrets
      name: no secrets
      entry: python3 examples/hooks/check_no_secrets.py
      language: system
```
`audit_log.py` and `check_no_secrets.py` are in `examples/hooks/`; they read the JSON event / file list and never print secrets.
