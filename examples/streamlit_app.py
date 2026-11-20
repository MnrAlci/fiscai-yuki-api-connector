"""Minimal Streamlit app on the read-only export layer. Example data: [Voorbeeld]. No Yuki key, no network calls.
Run:  pip install streamlit pandas   (optional, not part of the plugin)
      YUKI_EXPORT_DIR=./examples/data streamlit run examples/streamlit_app.py
Point YUKI_EXPORT_DIR at the folder you gave to yuki_export_dataset (export_map)."""
import os
from pathlib import Path

import pandas as pd
import streamlit as st

DIR = Path(os.environ.get("YUKI_EXPORT_DIR", Path(__file__).parent / "data"))
st.set_page_config(page_title="Yuki key figures (example)", layout="wide")
st.title("Key figures")
st.caption("EXAMPLE with made-up [Voorbeeld] data. Not tax advice; ask your accountant.")

kpis = pd.read_csv(DIR / "yuki-kpis.csv")
cols = st.columns(4)
for col, name in zip(cols, ["omzet", "kosten", "resultaat", "liquide_middelen"]):
    row = kpis[kpis["kpi"] == name]
    if not row.empty:
        col.metric(name.replace("_", " "), f"{row['waarde'].iloc[0]:,.0f} EUR")

posten = pd.read_csv(DIR / "yuki-openstaande_posten.csv")
st.subheader("Open debtors by age")
st.bar_chart(posten[posten["open_bedrag"] > 0].groupby("ouderdom_bucket")["open_bedrag"].sum())
st.subheader("Open items")
st.dataframe(posten, use_container_width=True)
st.caption("Powered by FISCALCI Accounting & Tax (Askin Alci)")
