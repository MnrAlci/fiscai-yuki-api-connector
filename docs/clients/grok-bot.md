# Grok Bot (recommended)

FISCAi Yuki API Connector is built as a plugin for Grok Bot: it ships a plugin manifest, an MCP server definition and a skill that tells Grok Bot how to use the tools safely.

## Steps

1. Install the plugin as described in the [README](../../README.md#install-in-grok-bot-recommended): Python 3.10+, `git clone`, a virtual environment, `pip install -r requirements.txt`.
2. Add the plugin folder to Grok Bot and fill in the variables it asks for. At minimum `YUKI_ACCESS_KEY`; set `YUKI_ACCESS_LEVEL` to `domein` (one administration) or `portaal` (portal key). Enter the key in Grok Bot's own settings, never in a file or in the chat. The exact menu names depend on your Grok Bot version.
3. Leave `YUKI_WRITE_ENABLED` unset. The plugin is read-only then.
4. Ask Grok Bot: "Run `yuki_status`", then "List my Yuki administrations".

The variable names are listed in [`examples/grok-bot.variables.env.example`](../../examples/grok-bot.variables.env.example) (placeholders only).

## Dashboards in Grok Bot

Grok Bot can turn the figures into a page or canvas; use the ready-made prompts in the [business owner guide](../business-owners/README.md#ready-made-prompts) or the [accountant guide](../accountants-portal/README.md#ready-made-prompts). The plugin's own `yuki_dashboard` tool also exports a static HTML dashboard to a folder you choose.

Config format checked against the client's official documentation on 2026-11-20. Not tested live in the client by the author; if something differs, follow the client's current documentation (verify current client docs).

Back to [all clients](README.md)

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
