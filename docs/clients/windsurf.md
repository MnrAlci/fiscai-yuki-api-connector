# Windsurf

Windsurf (Cascade) reads `~/.codeium/windsurf/mcp_config.json`. Docs: <https://docs.windsurf.com/windsurf/cascade/mcp> (verify current client docs; the file location and interpolation have changed between versions).

Config format checked against the client's official documentation on 2026-11-20. Not tested live in the client by the author; if something differs, follow the client's current documentation (verify current client docs).

## Steps

1. Install the plugin (README).
2. Set `YUKI_ACCESS_KEY` in the environment Windsurf is started from.
3. Add the server to `mcp_config.json`; Windsurf documents `${env:NAME}` interpolation in `command`, `args` and `env`.
4. Refresh the MCP list in Cascade.

## Example (`examples/windsurf.mcp_config.json`)

See [`examples/windsurf.mcp_config.json`](../../examples/windsurf.mcp_config.json). The key is a `${env:YUKI_ACCESS_KEY}` reference.

Replace `/ABSOLUTE/PATH/TO/fiscai-yuki-api-connector` with the folder where you installed the plugin (see the [README](../../README.md#install-in-grok-bot-recommended) for the install). Use `"domein"` for a single-administration key (business owner) or `"portaal"` for a portal key (accountant).

## Check it works

Ask: "Run `yuki_status`" (no Yuki call), then "List my Yuki administrations" (`yuki_administraties`). Writing stays off unless you set `YUKI_WRITE_ENABLED=ja` yourself; do not set it.

Back to [all clients](README.md) · [Business owners](../business-owners/README.md) · [Accountants](../accountants-portal/README.md)

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
