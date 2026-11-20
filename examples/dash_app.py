"""Minimal Plotly Dash app on the read-only export layer. Example data: [Voorbeeld]. No Yuki key, no network calls.
Run:  pip install dash pandas   (optional, not part of the plugin)
      YUKI_EXPORT_DIR=./examples/data python examples/dash_app.py   then open http://127.0.0.1:8050
Point YUKI_EXPORT_DIR at the folder you gave to yuki_export_dataset (export_map)."""
import os
from pathlib import Path

import pandas as pd
from dash import Dash, dash_table, dcc, html
import plotly.express as px

DIR = Path(os.environ.get("YUKI_EXPORT_DIR", Path(__file__).parent / "data"))
kpis = pd.read_csv(DIR / "yuki-kpis.csv")
posten = pd.read_csv(DIR / "yuki-openstaande_posten.csv")
ouder = posten[posten["open_bedrag"] > 0].groupby("ouderdom_bucket", as_index=False)["open_bedrag"].sum()

app = Dash(__name__)
app.layout = html.Div([
    html.H1("Key figures"),
    html.P("EXAMPLE with made-up [Voorbeeld] data. Not tax advice; ask your accountant."),
    dash_table.DataTable(kpis[["kpi", "waarde", "eenheid"]].to_dict("records"), [{"name": c, "id": c} for c in ("kpi", "waarde", "eenheid")]),
    dcc.Graph(figure=px.bar(ouder, x="ouderdom_bucket", y="open_bedrag", title="Open debtors by age")),
    html.Small("Powered by FISCALCI Accounting & Tax (Askin Alci)"),
], style={"fontFamily": "sans-serif", "maxWidth": "960px", "margin": "2rem auto"})

if __name__ == "__main__":
    app.run(host="127.0.0.1", debug=False)
