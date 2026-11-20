# python-docx and openpyxl

Licence: python-docx: MIT per its repository; openpyxl: verifieer actuele regel · Official site: <https://python-docx.readthedocs.io> · Free to use by default; no paid service is required.

Build DOCX and XLSX directly from the CSV exports in Python (openpyxl: <https://openpyxl.readthedocs.io>).

Facts below come from the vendor's official pages (linked); anything not confirmed there is marked *verify current docs* / `verifieer actuele regel`. Not tested live by the author.

## Input

Either the exported files from `yuki_export_dataset` (see [EXPORT-SCHEMA.md](../../EXPORT-SCHEMA.md); example data in [`examples/data/`](../../../examples/data/)) or text that Grok Bot wrote from the MCP output. Never put the Yuki key in a template.

## Minimal example

Template: [`examples/templates/kpi_to_docx_xlsx.py`](../../../examples/templates/kpi_to_docx_xlsx.py). Run from the `examples/` folder:

```bash
pip install python-docx openpyxl
python templates/kpi_to_docx_xlsx.py data/yuki-kpis.csv
```

Check the output before it goes to a client; the figures are read from Yuki as-is and are not tax advice.

> **Not tax advice.** The figures are read from your Yuki administration and shown as-is. Ask your accountant before acting on them. Not approved or endorsed by Yuki or Visma.

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
