# Microsoft Power Automate

Official site: <https://www.microsoft.com/power-platform/products/power-automate> · Pricing: commercial, some use included with Microsoft 365 plans (verify) (verifieer actuele regel) · Facts below come from the vendor's official pages (linked); anything not confirmed there is marked *verify current docs* / `verifieer actuele regel`. Not tested live by the author.

Cloud flows trigger on files in OneDrive/SharePoint (put the export folder there); desktop flows can work with local files (verify current docs). Fits Microsoft 365 offices.

## Two safe routes

1. **Export layer (recommended).** `yuki_export_dataset` writes CSV/JSON to a folder. The automation reads that folder (or a synced copy). The Yuki key never leaves the plugin. See [EXPORT-SCHEMA.md](../../EXPORT-SCHEMA.md).
2. **MCP server.** Only if the automation tool can run or reach a local MCP stdio server itself (self-hosted setups). Read-only: do not set `YUKI_WRITE_ENABLED`. Use the generic config in [`examples/generic-mcp-stdio.json`](../../../examples/generic-mcp-stdio.json) with the key as an environment reference.

## Rules

- No secrets in workflows, webhooks or screenshots; use the tool's secret store or environment variables.
- A workflow may **prepare** a message but never sends client figures to third parties without a human confirmation and the client's permission.
- Prefer aggregated figures (`kpis`) over detailed lists (`openstaande_posten`) when a cloud service is involved.

> **Not tax advice.** The figures are read from your Yuki administration and shown as-is. Ask your accountant before acting on them. Not approved or endorsed by Yuki or Visma.

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
