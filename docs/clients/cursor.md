# Cursor

Cursor reads MCP servers from `~/.cursor/mcp.json` (all projects) or `.cursor/mcp.json` (one project). Official docs: <https://cursor.com/docs/mcp>.

Config format checked against the client's official documentation on 2026-11-20. Not tested live in the client by the author; if something differs, follow the client's current documentation (verify current client docs).

## Steps

1. Install the plugin (README).
2. Set `YUKI_ACCESS_KEY` in the environment Cursor is started from, then restart Cursor.
3. Add the server to `mcp.json`; Cursor expands `${env:NAME}` in `command`, `args` and `env`.
4. Enable the server in Cursor's MCP settings.

## Example (`examples/cursor.mcp.json`)

See [`examples/cursor.mcp.json`](../../examples/cursor.mcp.json). The key is a `${env:YUKI_ACCESS_KEY}` reference, not a value.

Replace `/ABSOLUTE/PATH/TO/fiscai-yuki-api-connector` with the folder where you installed the plugin (see the [README](../../README.md#install-in-grok-bot-recommended) for the install). Use `"domein"` for a single-administration key (business owner) or `"portaal"` for a portal key (accountant).

## Check it works

Ask: "Run `yuki_status`" (no Yuki call), then "List my Yuki administrations" (`yuki_administraties`). Writing stays off unless you set `YUKI_WRITE_ENABLED=ja` yourself; do not set it.

Back to [all clients](README.md) · [Business owners](../business-owners/README.md) · [Accountants](../accountants-portal/README.md)

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
