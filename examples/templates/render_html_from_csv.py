"""Stdlib only: CSV from yuki_export_dataset -> HTML (for WeasyPrint, browser print or Pandoc). Usage: python render_html_from_csv.py ../data/yuki-kpis.csv > report.html"""
import csv
import html
import sys

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
print("<!doctype html><meta charset='utf-8'><style>body{font-family:sans-serif}td,th{border:1px solid #999;padding:4px 8px}table{border-collapse:collapse}</style>")
print("<h1>Key figures " + html.escape(rows[0]["administratie"]) + "</h1><table><tr><th>KPI</th><th>Value</th><th>Unit</th></tr>")
for r in rows:
    print("<tr><td>%s</td><td>%s</td><td>%s</td></tr>" % (html.escape(r["kpi"]), html.escape(r["waarde"]), html.escape(r["eenheid"])))
print("</table><p><em>Not tax advice; ask your accountant.</em></p>")
