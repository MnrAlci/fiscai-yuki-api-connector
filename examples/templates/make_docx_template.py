"""Creates templates/kpi-template.docx with {tags} (needs: pip install python-docx). For docxtemplater: {omzet}. For Carbone use its own tag syntax: {d.omzet} (verify current Carbone docs)."""
import sys
from docx import Document

tag = (lambda n: "{d." + n + "}") if "--carbone" in sys.argv else (lambda n: "{" + n + "}")
d = Document()
d.add_heading("Key figures " + tag("administratie"), 1)
for n in ("omzet", "kosten", "resultaat"):
    d.add_paragraph(f"{n}: {tag(n)} EUR")
d.add_paragraph("EXAMPLE with made-up [Voorbeeld] data. Not tax advice.")
d.save("kpi-template.docx")
