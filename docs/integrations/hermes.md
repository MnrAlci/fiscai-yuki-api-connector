# Hermes Agent (Nous Research)

**What it is.** [Hermes Agent](https://hermes-agent.nousresearch.com) is an open-source agent from Nous Research. It has native MCP support: stdio servers are configured in `~/.hermes/config.yaml` under `mcp_servers` with `command`, `args` and `env` (official docs: <https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference>). Secrets can be referenced as `${NAME}` and kept in `~/.hermes/.env`.

**Is there a Yuki-specific "Hermes plugin"?** No. FISCAi Yuki API Connector is a normal MCP stdio server and Hermes Agent can start it. We do not ship a separate Hermes plugin.

## Setup

1. Install FISCAi Yuki API Connector (README) and note the absolute paths.
2. Put `YUKI_ACCESS_KEY=...` in `~/.hermes/.env` (a private file on your computer).
3. Merge [`examples/hermes.config.yaml`](../../examples/hermes.config.yaml) into `~/.hermes/config.yaml`. It also contains the optional hosted AgentMail entry (`url` + `headers`); delete it if you do not use AgentMail.
4. Restart Hermes Agent and ask it to list its tools. Optionally restrict tools with the documented `tools: include/exclude` filter.

*verify current docs* Option names such as `tools` or `timeout` change between Hermes versions; check the reference above.

## Safety rules for this integration

- Yuki stays **read-only**: do not set `YUKI_WRITE_ENABLED`.
- Nothing is sent automatically: the agent prepares a **draft**, you read it and confirm every send.
- The Yuki key and any other key stay on your own computer, as environment variables or in the platform's secret store, never in a repository or in the chat.
- Do not send client data to third parties (including mail or agent services) without the client's permission.

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
