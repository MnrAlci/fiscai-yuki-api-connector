# Quarto

Licence: verifieer actuele regel · Official site: <https://quarto.org> · Free to use by default; no paid service is required.

Reports from `.qmd` notebooks with live code, rendered to HTML, DOCX or PDF.

Facts below come from the vendor's official pages (linked); anything not confirmed there is marked *verify current docs* / `verifieer actuele regel`. Not tested live by the author.

## Input

Either the exported files from `yuki_export_dataset` (see [EXPORT-SCHEMA.md](../../EXPORT-SCHEMA.md); example data in [`examples/data/`](../../../examples/data/)) or text that Grok Bot wrote from the MCP output. Never put the Yuki key in a template.

## Minimal example

Template: [`examples/templates/quarto-report.qmd`](../../../examples/templates/quarto-report.qmd). Run from the `examples/` folder:

```bash
quarto render templates/quarto-report.qmd --to docx
quarto render templates/quarto-report.qmd --to html
```

Check the output before it goes to a client; the figures are read from Yuki as-is and are not tax advice.

> **Not tax advice.** The figures are read from your Yuki administration and shown as-is. Ask your accountant before acting on them. Not approved or endorsed by Yuki or Visma.

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
