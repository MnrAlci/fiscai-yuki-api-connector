# Pandoc

Licence: GPL-2.0 per the project repository (verify the current line) · Official site: <https://pandoc.org> · Free to use by default; no paid service is required.

Converts Markdown to DOCX, PDF (via an engine such as Typst, WeasyPrint or LaTeX), HTML.

Facts below come from the vendor's official pages (linked); anything not confirmed there is marked *verify current docs* / `verifieer actuele regel`. Not tested live by the author.

## Input

Either the exported files from `yuki_export_dataset` (see [EXPORT-SCHEMA.md](../../EXPORT-SCHEMA.md); example data in [`examples/data/`](../../../examples/data/)) or text that Grok Bot wrote from the MCP output. Never put the Yuki key in a template.

## Minimal example

Template: [`examples/templates/pandoc-report.md`](../../../examples/templates/pandoc-report.md). Run from the `examples/` folder:

```bash
pandoc templates/pandoc-report.md -o kpi-report.docx
pandoc templates/pandoc-report.md -o kpi-report.pdf --pdf-engine=weasyprint
```

Check the output before it goes to a client; the figures are read from Yuki as-is and are not tax advice.

> **Not tax advice.** The figures are read from your Yuki administration and shown as-is. Ask your accountant before acting on them. Not approved or endorsed by Yuki or Visma.

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
