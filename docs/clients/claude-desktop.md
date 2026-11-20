# Claude Desktop

Claude Desktop reads local MCP servers from `claude_desktop_config.json` (macOS: `~/Library/Application Support/Claude/`, Windows: `%APPDATA%\Claude\`). Official guide: <https://modelcontextprotocol.io/docs/develop/connect-local-servers>.

Config format checked against the client's official documentation on 2026-11-20. Not tested live in the client by the author; if something differs, follow the client's current documentation (verify current client docs).

## Steps

1. Install the plugin (README).
2. Open Claude Desktop settings, Developer, Edit Config, and add the server.
3. Claude Desktop's documented `env` block takes literal values (no `${...}` expansion is documented; verify current client docs). So the key sits in this one local file: keep the file private, never copy it into a repository, chat or backup that others can read.
4. Fully quit and restart Claude Desktop.

## Example (`examples/claude-desktop.config.json`)

See [`examples/claude-desktop.config.json`](../../examples/claude-desktop.config.json). `YOUR_YUKI_ACCESS_KEY` is a placeholder you replace locally.

Replace `/ABSOLUTE/PATH/TO/fiscai-yuki-api-connector` with the folder where you installed the plugin (see the [README](../../README.md#install-in-grok-bot-recommended) for the install). Use `"domein"` for a single-administration key (business owner) or `"portaal"` for a portal key (accountant).

## Check it works

Ask: "Run `yuki_status`" (no Yuki call), then "List my Yuki administrations" (`yuki_administraties`). Writing stays off unless you set `YUKI_WRITE_ENABLED=ja` yourself; do not set it.

Back to [all clients](README.md) · [Business owners](../business-owners/README.md) · [Accountants](../accountants-portal/README.md)

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
