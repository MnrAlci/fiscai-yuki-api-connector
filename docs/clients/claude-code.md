# Claude Code

Claude Code uses `claude mcp add` or a project `.mcp.json`. Official docs: <https://code.claude.com/docs/en/mcp>.

Config format checked against the client's official documentation on 2026-11-20. Not tested live in the client by the author; if something differs, follow the client's current documentation (verify current client docs).

## Steps

1. Install the plugin (README).
2. `export YUKI_ACCESS_KEY=...` in your shell (do not put it in the command history of a shared machine), then add the server with a `.mcp.json` like the example. Claude Code expands `${VAR}` and `${VAR:-default}` in `command`, `args` and `env`.
3. Or use the CLI: `claude mcp add --transport stdio --env YUKI_ACCESS_LEVEL=domein fiscai-yuki-api-connector -- /ABSOLUTE/PATH/TO/fiscai-yuki-api-connector/.venv/bin/python /ABSOLUTE/PATH/TO/fiscai-yuki-api-connector/server/run_server.py` and pass the key through the environment.
4. Approve the project server when Claude Code asks, then check `/mcp`.

## Example (`examples/claude-code.mcp.json`)

See [`examples/claude-code.mcp.json`](../../examples/claude-code.mcp.json). Unset variables stay literal (`${YUKI_ACCESS_KEY}`) and Claude Code warns in `claude mcp list`.

Replace `/ABSOLUTE/PATH/TO/fiscai-yuki-api-connector` with the folder where you installed the plugin (see the [README](../../README.md#install-in-grok-bot-recommended) for the install). Use `"domein"` for a single-administration key (business owner) or `"portaal"` for a portal key (accountant).

## Check it works

Ask: "Run `yuki_status`" (no Yuki call), then "List my Yuki administrations" (`yuki_administraties`). Writing stays off unless you set `YUKI_WRITE_ENABLED=ja` yourself; do not set it.

Back to [all clients](README.md) · [Business owners](../business-owners/README.md) · [Accountants](../accountants-portal/README.md)

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
