# Client guides

FISCAi Yuki API Connector is **first and foremost a plugin for Grok Bot**. It is a standard MCP stdio server, so other clients work too.

| Client | Guide | Example config | Secret handling |
|---|---|---|---|
| **Grok Bot** (recommended) | [grok-bot.md](grok-bot.md) | [grok-bot.variables.env.example](../../examples/grok-bot.variables.env.example) | Grok Bot settings |
| Cursor | [cursor.md](cursor.md) | [cursor.mcp.json](../../examples/cursor.mcp.json) | `${env:...}` |
| Claude Desktop | [claude-desktop.md](claude-desktop.md) | [claude-desktop.config.json](../../examples/claude-desktop.config.json) | local file |
| Claude Code | [claude-code.md](claude-code.md) | [claude-code.mcp.json](../../examples/claude-code.mcp.json) | `${VAR}` |
| GitHub Copilot (VS Code) | [github-copilot-vscode.md](github-copilot-vscode.md) | [vscode.mcp.json](../../examples/vscode.mcp.json) | `${input:...}` |
| Windsurf | [windsurf.md](windsurf.md) | [windsurf.mcp_config.json](../../examples/windsurf.mcp_config.json) | `${env:...}` |
| Generic MCP client | [generic-mcp-client.md](generic-mcp-client.md) | [generic-mcp-stdio.json](../../examples/generic-mcp-stdio.json) | depends |
| Hermes Agent, OpenClaw, AgentMail | [integrations](../integrations/README.md) | see there | env file / env reference |

Config format checked against the client's official documentation on 2026-11-20. Not tested live in the client by the author; if something differs, follow the client's current documentation (verify current client docs).

Powered by FISCALCI Accounting & Tax (Askin Alci)
