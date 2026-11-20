# Data collection tools (outside data next to your Yuki figures)

Use case: bring **outside** data in next to the Yuki figures, for example a supplier's public price list or public company information, and compare them in a sheet or dashboard. The plugin itself does not collect or scrape anything.

| Tool | What it does | Official site | Paid? |
|---|---|---|---|
| Thunderbit | AI web scraper that extracts structured data from web pages, PDFs and images (per its own blog) | <https://thunderbit.com> | free tier and paid plans exist per the vendor: verifieer actuele regel |
| KoboToolbox / ODK | Forms and field data collection, open-source | <https://www.kobotoolbox.org>, <https://getodk.org> | verifieer actuele regel |
| Google Forms, Typeform, Jotform | Online forms and surveys | <https://forms.google.com>, <https://www.typeform.com>, <https://www.jotform.com> | verifieer actuele regel |
| Airtable | Database with forms | <https://airtable.com> | verifieer actuele regel |

The overview of such tools that Askin referred to is a vendor blog (<https://thunderbit.com/nl/blog/best-data-collection-software-tools>); treat comparisons there as marketing and check each tool's own site.

## How to combine

1. Collect the outside data into a CSV/Excel file (supplier prices, public data).
2. Export the Yuki side with `yuki_export_dataset` (for example `openstaande_posten`).
3. Combine both in a spreadsheet or a dashboard tool from the [visualisation guides](../visualisatie/README.md).

## Warnings (read first)

- **GDPR and privacy law.** Personal data (names, e-mail addresses, phone numbers) falls under the GDPR even when it is public. Only collect what you need and have a legal basis.
- **Terms of use.** Check the site's terms and `robots.txt` before scraping; many sites forbid automated collection. Prefer an official API or a price list the supplier sends you.
- **Never put client data in a third-party service.** Do not upload Yuki exports, client names or figures to a scraping or form tool. Collect outside data only; join it with Yuki data locally.
- Paid options are marked; nothing here is required to use the plugin.

> **Not tax advice.** The figures are read from your Yuki administration and shown as-is. Ask your accountant before acting on them. Not approved or endorsed by Yuki or Visma.

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
