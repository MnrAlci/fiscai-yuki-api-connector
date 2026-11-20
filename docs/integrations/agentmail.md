# AgentMail

**What it is.** [AgentMail](https://www.agentmail.to) is an email service for AI agents: agents get their own inboxes and can read, draft and send mail through an API. It publishes an official MCP server, hosted at `https://mcp.agentmail.to/mcp`, and an npm/PyPI stdio bridge `agentmail-mcp` for clients that only speak stdio (docs: <https://docs.agentmail.to/integrations/mcp>).

**What this integration is.** AgentMail does not plug into FISCAi Yuki API Connector; you run **both MCP servers side by side** in the same client. FISCAi Yuki API Connector reads the figures locally, AgentMail provides the mailbox. There is no code of ours that talks to AgentMail. Check AgentMail's current pricing and terms yourself; creating an account and key is your own decision (verify current docs).

## Setup

1. Install FISCAi Yuki API Connector in your client first (see [client guides](../clients/README.md)).
2. Create an AgentMail API key in its console (Settings, API Keys, per AgentMail's docs) and keep it in an environment variable `AGENTMAIL_API_KEY`.
3. Add AgentMail as a second server.
   - Remote (preferred when the client supports headers): [`examples/agentmail-hosted.mcp.json`](../../examples/agentmail-hosted.mcp.json) (`x-api-key` header from `${env:AGENTMAIL_API_KEY}`). Clients with OAuth support (for example Claude) can use the bare URL instead, without a key.
   - stdio bridge: [`examples/agentmail-stdio.mcp.json`](../../examples/agentmail-stdio.mcp.json) (`npx -y agentmail-mcp`, Node.js 20+). `--tools list_inboxes,...` limits the exposed tools (check the real tool names in your client first).
4. Restart the client and check that both servers list their tools.

## Example scenario: periodic KPI mail (business owner)

1. You ask: "Read my key figures for this month with `yuki_dashboard_kpis` and write a short summary for me."
2. The agent reads Yuki locally (read-only) and writes a plain summary.
3. The agent creates an **AgentMail draft** addressed to **your own** address.
4. You read the draft. Only after you say "send" does the agent send it. A schedule (if your platform has one) may *prepare* the draft but must never send without your confirmation.

## Example scenario: file overview (accountant)

Same flow with `yuki_portfolio_kpis`, but only for files where the client agreed that figures may be mailed. Prefer sending to yourself or to the client's own address, and keep the summary short. Mail passes through AgentMail's servers: that is a third party.

## Safety rules for this integration

- Yuki stays **read-only**: do not set `YUKI_WRITE_ENABLED`.
- Nothing is sent automatically: the agent prepares a **draft**, you read it and confirm every send.
- The Yuki key and any other key stay on your own computer, as environment variables or in the platform's secret store, never in a repository or in the chat.
- Do not send client data to third parties (including mail or agent services) without the client's permission.
- Mail via AgentMail leaves your computer. Mail only what you would accept to send by any other external mail service.

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
