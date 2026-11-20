# OpenClaw

**What it is.** [OpenClaw](https://docs.openclaw.ai) is an agent gateway with a managed MCP registry. Servers live under `mcp.servers` in its config (`~/.openclaw/openclaw.json`); stdio entries use `command`, `args` and `env`. You can also manage them with the `openclaw mcp` commands (`add`, `list`, `doctor --probe`) or in the Control UI (official docs: <https://docs.openclaw.ai/tools/mcp>, <https://docs.openclaw.ai/gateway/config-extensions>).

**Is there a Yuki-specific "OpenClaw plugin"?** No. OpenClaw starts FISCAi Yuki API Connector as a normal MCP stdio server. We do not ship a separate OpenClaw plugin.

## Setup

1. Install FISCAi Yuki API Connector (README) and note the absolute paths.
2. Add the server from [`examples/openclaw.mcp.json`](../../examples/openclaw.mcp.json) to `mcp.servers` (or use `openclaw mcp add`). The example also has an optional AgentMail bridge entry; remove it if unused.
3. Provide `YUKI_ACCESS_KEY` through OpenClaw's supported secret mechanism or the gateway's environment. OpenClaw's docs advise keeping credentials out of config literals; whether `${VAR}` is expanded in `env` depends on your version (*verify current docs*).
4. Run `openclaw mcp doctor fiscai-yuki-api-connector --probe` to check the connection.

OpenClaw drops some loader/interpreter variables from stdio `env` for safety; `YUKI_*` variables are ordinary and unaffected.

## Safety rules for this integration

- Yuki stays **read-only**: do not set `YUKI_WRITE_ENABLED`.
- Nothing is sent automatically: the agent prepares a **draft**, you read it and confirm every send.
- The Yuki key and any other key stay on your own computer, as environment variables or in the platform's secret store, never in a repository or in the chat.
- Do not send client data to third parties (including mail or agent services) without the client's permission.

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
