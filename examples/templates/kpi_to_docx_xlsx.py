"""CSV from yuki_export_dataset -> DOCX (python-docx) and XLSX (openpyxl). Needs: pip install python-docx openpyxl
Usage: python kpi_to_docx_xlsx.py ../data/yuki-kpis.csv"""
import csv
import sys
from docx import Document
from openpyxl import Workbook

rows = list(csv.DictReader(open(sys.argv[1], encoding="utf-8")))
d = Document()
d.add_heading("Key figures " + rows[0]["administratie"], 1)
t = d.add_table(rows=1, cols=3)
for c, h in zip(t.rows[0].cells, ("KPI", "Value", "Unit")):
    c.text = h
for r in rows:
    cells = t.add_row().cells
    cells[0].text, cells[1].text, cells[2].text = r["kpi"], r["waarde"], r["eenheid"]
d.add_paragraph("EXAMPLE or real figures: not tax advice; ask your accountant.")
d.save("kpi-report.docx")
wb = Workbook()
ws = wb.active
ws.append(["kpi", "waarde", "eenheid"])
for r in rows:
    ws.append([r["kpi"], float(r["waarde"]), r["eenheid"]])
wb.save("kpi-report.xlsx")
