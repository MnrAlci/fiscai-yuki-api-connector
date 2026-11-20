# Visualisation and data apps

One neutral layer feeds every tool: the read-only export `yuki_export_dataset` writes CSV, JSON, Excel (xlsx) and Parquet with a fixed schema ([EXPORT-SCHEMA.md](../../EXPORT-SCHEMA.md)). No tool below receives your Yuki key. Paid options are marked; prices and licences: verifieer actuele regel on the official page.

| Tool | Type | Official site |
|---|---|---|
| [Power BI](power-bi.md) | commercial (Desktop offered free by Microsoft) | https://powerbi.microsoft.com |
| [Qlik Sense](qlik-sense.md) | commercial | https://www.qlik.com |
| [Domo](domo.md) | commercial | https://www.domo.com |
| [Google Looker Studio (and Looker)](looker-studio.md) | Looker Studio: free to use per Google (verify); Looker: commercial | https://lookerstudio.google.com |
| [Tableau](tableau.md) | commercial; Tableau Public publishes everything publicly | https://www.tableau.com |
| [Lovable](lovable.md) | commercial, free tier may exist | https://lovable.dev |
| [Metabase](metabase.md) | open-source edition and commercial plans | https://www.metabase.com |
| [Apache Superset](apache-superset.md) | open-source, Apache-2.0 per the project repository | https://superset.apache.org |
| [Grafana](grafana.md) | open-source (AGPL-3.0 per the project repository), cloud and enterprise plans | https://grafana.com |
| [Streamlit](streamlit.md) | open-source Python framework | https://streamlit.io |
| [Plotly Dash](plotly-dash.md) | open-source Python framework (Plotly also sells enterprise products) | https://dash.plotly.com |
| [Hex](hex.md) | commercial, free tier may exist | https://hex.tech |
| [Snowflake](snowflake.md) | PAID cloud data platform: you need your own account | https://www.snowflake.com |

Nederlandse samenvatting: elke tool leest dezelfde exportbestanden (CSV, JSON, xlsx, Parquet) uit een map; de Yuki-sleutel blijft in de plugin. Streamlit en Dash hebben een klein voorbeeld in `examples/` met `[Voorbeeld]`-data. Betaalde diensten (Snowflake en de meeste commerciële BI) zijn duidelijk gemarkeerd; zet geen klantgegevens in een cloudtool zonder toestemming.

> **Not tax advice.** The figures are read from your Yuki administration and shown as-is. Ask your accountant before acting on them. Not approved or endorsed by Yuki or Visma.

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
