# Snowflake

Type: PAID cloud data platform: you need your own account · Pricing/licence: Paid; verifieer actuele regel · Official site: <https://www.snowflake.com>

A cloud data warehouse, for larger portfolios.

Facts below come from the vendor's official pages (linked); anything not confirmed there is marked *verify current docs* / `verifieer actuele regel`. Not tested live by the author.

Step 0 is always the same: run the read-only tool `yuki_export_dataset` (datasets `kpis`, `saldi`, `openstaande_posten`; formats `csv`, `json`, `xlsx`, `parquet`) with an `export_map` folder. The fixed columns are in [EXPORT-SCHEMA.md](../../EXPORT-SCHEMA.md). Example files with `[Voorbeeld]` data: [`examples/data/`](../../../examples/data/).

## 1. File or folder import

Upload the export through an internal stage and `COPY INTO` a table; see [`examples/snowflake-load.sql`](../../../examples/snowflake-load.sql) (verify current Snowflake docs for PUT and COPY).

## 2. Scheduled refresh

Re-run PUT and COPY INTO after each export (you can script this).

Refresh: there is no background service. Ask Grok Bot (or the scheduler of your agent platform, if it has one: verify) to run `yuki_export_dataset` again into the same folder; then refresh in the tool. Your Yuki key stays in the plugin and is never given to the tool below.

## 3. Optional local HTTP/JSON endpoint

Not applicable.

Optional local HTTP/JSON: `python3 -m http.server 8765 --bind 127.0.0.1 --directory /path/to/export` serves the export folder read-only on your own computer (standard library, no key involved). Stop it when you are done. Cloud tools cannot reach `127.0.0.1`.

## Privacy

Data leaves your computer to a cloud warehouse: only with the client's permission; check where the account's region is hosted. Never put your Yuki key into any of these tools: they only need the exported files.

> **Not tax advice.** The figures are read from your Yuki administration and shown as-is. Ask your accountant before acting on them. Not approved or endorsed by Yuki or Visma.

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
