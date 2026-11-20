# GitHub Copilot (VS Code)

VS Code reads MCP servers from `.vscode/mcp.json` (workspace) or your user profile. Official docs: <https://code.visualstudio.com/docs/agents/reference/mcp-configuration>. The top-level keys are `servers` and `inputs`.

Config format checked against the client's official documentation on 2026-11-20. Not tested live in the client by the author; if something differs, follow the client's current documentation (verify current client docs).

## Steps

1. Install the plugin (README).
2. Create `.vscode/mcp.json` like the example. The `promptString` input with `password: true` makes VS Code ask for the key once and store it itself, so no key is in the file.
3. Start the server from the editor (MCP: List Servers) and use it in Agent mode. Tool approvals still apply.

## Example (`examples/vscode.mcp.json`)

See [`examples/vscode.mcp.json`](../../examples/vscode.mcp.json). VS Code format only; `inputs` is not supported in the portable `.mcp.json` format.

Replace `/ABSOLUTE/PATH/TO/fiscai-yuki-api-connector` with the folder where you installed the plugin (see the [README](../../README.md#install-in-grok-bot-recommended) for the install). Use `"domein"` for a single-administration key (business owner) or `"portaal"` for a portal key (accountant).

## Check it works

Ask: "Run `yuki_status`" (no Yuki call), then "List my Yuki administrations" (`yuki_administraties`). Writing stays off unless you set `YUKI_WRITE_ENABLED=ja` yourself; do not set it.

Back to [all clients](README.md) · [Business owners](../business-owners/README.md) · [Accountants](../accountants-portal/README.md)

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
