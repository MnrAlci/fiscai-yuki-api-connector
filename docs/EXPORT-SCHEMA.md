# Export schema (fixed)

The read-only tool `yuki_export_dataset` writes these datasets as `yuki-<dataset>.csv|json|xlsx|parquet` into the folder you choose (`export_map`). Columns, order and names are stable; new columns are only added at the end in a new version (see the CHANGELOG). Dates are `YYYY-MM-DD`, numbers use a dot, amounts are in the administration's currency. Parquet needs the optional `pyarrow` package. Example files with `[Voorbeeld]` data: [`examples/data/`](../examples/data/).


## `kpis`

| Column | Type | Meaning |
|---|---|---|
| `administratie` | text | Naam van de administratie |
| `periode_van` | date | Begin van de periode (JJJJ-MM-DD) |
| `periode_tot` | date | Einde van de periode |
| `peildatum` | date | Peildatum van de open posten |
| `kpi` | text | Naam van de kerncijfer, bv. omzet, kosten, resultaat, liquide_middelen, open_debiteuren_totaal |
| `waarde` | number | Waarde van het kerncijfer |
| `eenheid` | text | EUR, dagen, procent of aantal |

## `saldi`

| Column | Type | Meaning |
|---|---|---|
| `administratie` | text | Naam van de administratie |
| `peildatum` | date | Datum van de saldibalans |
| `rekening_code` | text | Grootboekrekening |
| `rekening_naam` | text | Naam van de rekening |
| `saldo` | number | Saldo = debet - credit |

## `openstaande_posten`

| Column | Type | Meaning |
|---|---|---|
| `administratie` | text | Naam van de administratie |
| `soort` | text | debiteuren of crediteuren |
| `peildatum` | date | Peildatum |
| `relatie` | text | Naam van de relatie |
| `referentie` | text | Referentie of factuurnummer |
| `omschrijving` | text | Omschrijving |
| `factuurdatum` | date | Factuurdatum |
| `vervaldatum` | date | Vervaldatum |
| `origineel_bedrag` | number | Oorspronkelijk bedrag |
| `open_bedrag` | number | Open bedrag (negatief = na te gaan) |
| `ouderdom_bucket` | text | niet_vervallen, 0-30, 31-60, 61-90, >90, zonder_datum of negatief |

The JSON file wraps the rows: `{ "dataset", "schema", "administratie", "bronnen", "rijen": [...] }`.

No file contains your Yuki key. Exports contain real figures when you run the tool on a real administration: store them like client data.

> **Not tax advice.** The figures are read from your Yuki administration and shown as-is. Ask your accountant before acting on them. Not approved or endorsed by Yuki or Visma.

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
