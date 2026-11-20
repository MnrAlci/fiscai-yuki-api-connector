# AGENTS.md

Guidance for AI coding agents and assistants working in this repository.

Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.

Powered by FISCALCI Accounting & Tax (Askin Alci)

## What this repo is
FISCAi Yuki API Connector: a local MCP server (Python, stdio) with read-only access to Yuki (Visma). Ready-made agent definitions are in [agents/](agents/README.md).

## Rules
- Read-only by default. Never enable or document enabling `YUKI_WRITE_ENABLED` in examples; never add write calls outside the gated booking workflow.
- No secrets, keys or real client data anywhere (code, tests, docs, fixtures). Use `[Voorbeeld]` data.
- Keep tool names (`yuki_*`) stable. Keep the "Powered by" line and the Belgian notice in docs.
- Run `make test` and `make lint` before proposing changes. Tests make no network calls.
- Mark unverified facts "verify current docs".
