"""Neutrale exportlaag: vaste, gedocumenteerde datasets naar CSV, JSON, Excel (xlsx) en Parquet.
Alleen lokale bestanden in een map naar keuze; geen Yuki-schrijfmethodes. Excel wordt zonder externe bibliotheek geschreven;
Parquet vraagt de optionele bibliotheek pyarrow."""
from __future__ import annotations

import csv
import io
import json
import zipfile
from pathlib import Path
from typing import Any
from xml.sax.saxutils import escape

SCHEMAS: dict[str, list[tuple[str, str, str]]] = {
    "kpis": [("administratie", "text", "Naam van de administratie"), ("periode_van", "date", "Begin van de periode (JJJJ-MM-DD)"),
             ("periode_tot", "date", "Einde van de periode"), ("peildatum", "date", "Peildatum van de open posten"),
             ("kpi", "text", "Naam van de kerncijfer, bv. omzet, kosten, resultaat, liquide_middelen, open_debiteuren_totaal"),
             ("waarde", "number", "Waarde van het kerncijfer"), ("eenheid", "text", "EUR, dagen, procent of aantal")],
    "saldi": [("administratie", "text", "Naam van de administratie"), ("peildatum", "date", "Datum van de saldibalans"),
              ("rekening_code", "text", "Grootboekrekening"), ("rekening_naam", "text", "Naam van de rekening"),
              ("saldo", "number", "Saldo = debet - credit")],
    "openstaande_posten": [("administratie", "text", "Naam van de administratie"), ("soort", "text", "debiteuren of crediteuren"),
                           ("peildatum", "date", "Peildatum"), ("relatie", "text", "Naam van de relatie"), ("referentie", "text", "Referentie of factuurnummer"),
                           ("omschrijving", "text", "Omschrijving"), ("factuurdatum", "date", "Factuurdatum"), ("vervaldatum", "date", "Vervaldatum"),
                           ("origineel_bedrag", "number", "Oorspronkelijk bedrag"), ("open_bedrag", "number", "Open bedrag (negatief = na te gaan)"),
                           ("ouderdom_bucket", "text", "niet_vervallen, 0-30, 31-60, 61-90, >90, zonder_datum of negatief")],
}
FORMATS = ("csv", "json", "xlsx", "parquet")


def cols(dataset: str) -> list[str]:
    return [c for c, _, _ in SCHEMAS[dataset]]


def _col(i: int) -> str:
    s = ""
    i += 1
    while i:
        i, r = divmod(i - 1, 26)
        s = chr(65 + r) + s
    return s


def write_csv(path: Path, dataset: str, rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cols(dataset), extrasaction="ignore")
        w.writeheader()
        w.writerows(rows)


def write_json(path: Path, dataset: str, rows: list[dict], meta: dict) -> None:
    path.write_text(json.dumps({"dataset": dataset, "schema": [{"naam": c, "type": t, "omschrijving": o} for c, t, o in SCHEMAS[dataset]],
                                **meta, "rijen": [{c: r.get(c) for c in cols(dataset)} for r in rows]}, ensure_ascii=False, indent=2), encoding="utf-8")


def write_xlsx(path: Path, dataset: str, rows: list[dict]) -> None:
    """Minimale xlsx (één blad, tekst en getallen) met alleen de standaardbibliotheek."""
    names = cols(dataset)
    types = {c: t for c, t, _ in SCHEMAS[dataset]}

    def cell(ref: str, v: Any, t: str) -> str:
        if v is None or v == "":
            return ""
        if t == "number" and isinstance(v, (int, float)):
            return f'<c r="{ref}"><v>{v}</v></c>'
        return f'<c r="{ref}" t="inlineStr"><is><t>{escape(str(v))}</t></is></c>'

    body = ['<row r="1">' + "".join(cell(f"{_col(i)}1", n, "text") for i, n in enumerate(names)) + "</row>"]
    for k, r in enumerate(rows, start=2):
        body.append(f'<row r="{k}">' + "".join(cell(f"{_col(i)}{k}", r.get(n), types[n]) for i, n in enumerate(names)) + "</row>")
    sheet = ('<?xml version="1.0" encoding="UTF-8" standalone="yes"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
             + "".join(body) + "</sheetData></worksheet>")
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": f'<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="{dataset[:31]}" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": sheet,
    }
    with zipfile.ZipFile(path, "w", zipfile.ZIP_DEFLATED) as z:
        for n, c in parts.items():
            z.writestr(n, c)


def write_parquet(path: Path, dataset: str, rows: list[dict]) -> None:
    try:
        import pyarrow as pa  # type: ignore
        import pyarrow.parquet as pq  # type: ignore
    except ImportError as exc:
        raise ValueError("Parquet vraagt de optionele bibliotheek pyarrow (pip install pyarrow). Kies anders csv, json of xlsx.") from exc
    types = {c: (pa.float64() if t == "number" else pa.string()) for c, t, _ in SCHEMAS[dataset]}
    data = {c: [r.get(c) if types[c] == pa.float64() else (None if r.get(c) is None else str(r.get(c))) for r in rows] for c in cols(dataset)}
    pq.write_table(pa.table({c: pa.array(v, type=types[c]) for c, v in data.items()}), str(path))


def write_all(folder: Path, dataset: str, rows: list[dict], formats: list[str], meta: dict) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for f in formats:
        p = folder / f"yuki-{dataset}.{f}"
        {"csv": lambda: write_csv(p, dataset, rows), "json": lambda: write_json(p, dataset, rows, meta),
         "xlsx": lambda: write_xlsx(p, dataset, rows), "parquet": lambda: write_parquet(p, dataset, rows)}[f]()
        out.append(str(p))
    return out


def schema_doc(dataset: str) -> list[dict]:
    return [{"naam": c, "type": t, "omschrijving": o} for c, t, o in SCHEMAS[dataset]]
