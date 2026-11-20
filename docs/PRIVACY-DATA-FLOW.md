# Privacy and data flow

> Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.

This page states what leaves your machine. It is a technical description, not legal advice; check your own GDPR obligations (processing agreement, client consent, retention).

## What the connector does
- Runs **locally** on your computer as an MCP server over stdio. There is no central server and no telemetry in this project.
- Talks to **one external service only**: the Yuki web services (Visma), using your own key, over HTTPS.
- Stores a local cache, a daily call counter and (optional booking workflow) an audit log in `YUKI_DATA_DIR`. The cache is encrypted; files are private to your user (mode 0600).

## What reaches your AI client
Tool results (figures, open items, analyses) are returned to the MCP client you use, and from there to **that client's AI provider** under that provider's terms. This is the main data flow to assess: decide per client which administrations you expose, and prefer a client and plan that match your confidentiality needs. Do not connect client data to tools you have no agreement with.

## What never leaves
Your Yuki key is only read from the environment and sent to Yuki. It is never part of tool output, logs or the cache index.

## Exports and integrations
- The export layer writes CSV, JSON, xlsx or Parquet **only to the folder you choose**. What you do with the files next (BI tools, document generators, automation services) is your responsibility; cloud services process data outside your machine.
- Prefer self-hosted or local options (for example n8n self-hosted, local Streamlit) for real client data. See `docs/integrations/`.
- The draft mails the plugin writes are `.eml` files. Nothing is sent by the plugin.

## Examples and tests
Everything in `examples/` and `tests/` is synthetic `[Voorbeeld]` data.

Powered by FISCALCI Accounting & Tax (Askin Alci)
