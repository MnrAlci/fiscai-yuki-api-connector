"""Controle ná het afhandelen in de Yuki-backoffice: staat het document nog in de workflow? Alleen lezen (Backoffice.GetWorkflow).
Het antwoordformaat van GetWorkflow is niet gedocumenteerd (resultaat is 'xml'); daarom zoekt deze helper het document-ID in alle waarden
en meldt 'onbepaald' (verifieer in de interface) als er geen ID-velden herkend worden."""
from __future__ import annotations

import re
from typing import Any

NOG = "nog in de workflow"
WEG = "niet meer in de workflow"
ONBEPAALD = "onbepaald"


def _norm(x: Any) -> str:
    return re.sub(r"[^a-z0-9]", "", str(x or "").casefold())


def _vlak(o: Any, sleutel: str = "") -> list[tuple[str, str]]:
    uit: list[tuple[str, str]] = []
    if isinstance(o, dict):
        for k, v in o.items():
            uit += _vlak(v, str(k))
    elif isinstance(o, (list, tuple)):
        for v in o:
            uit += _vlak(v, sleutel)
    elif o is not None:
        uit.append((sleutel, str(o)))
    return uit


def document_id(raw: Any) -> str:
    t = str(raw or "").strip()
    return t.split(":", 1)[1] if t[:2] in ("D:", "W:") else t


def beoordeel(workflow: Any, doc_id: str) -> dict:
    doc = _norm(document_id(doc_id))
    if len(doc) < 4:
        raise ValueError("Geef een geldig document-ID (zoals in het voorstel: 'D:<id>').")
    paren = _vlak(workflow)
    gevonden = [k for k, v in paren if _norm(v) == doc or (len(doc) >= 16 and doc in _norm(v))]
    id_velden = [k for k, _ in paren if re.sub(r"[^a-z]", "", k.casefold()).endswith("id")]
    if gevonden:
        return {"uitkomst": NOG, "afgehandeld": False, "zekerheid": "hoog", "uitleg": "Het document staat nog in GetWorkflow.", "workflowitems": len(paren)}
    if not paren:
        return {"uitkomst": WEG, "afgehandeld": True, "zekerheid": "midden",
                "uitleg": "GetWorkflow is leeg: het document staat niet meer in de workflow. Dat bewijst niet op zich dat het afgehandeld is (het kan ook verplaatst of verwijderd zijn): bekijk de backoffice-status.",
                "workflowitems": 0}
    if id_velden:
        return {"uitkomst": WEG, "afgehandeld": True, "zekerheid": "midden",
                "uitleg": "Het document staat niet meer in GetWorkflow (de lijst bevat wel ID-velden). Niet in de workflow betekent waarschijnlijk afgehandeld, maar ook verplaatst of verwijderd is mogelijk: verifieer in de interface (status 'Afgehandeld').",
                "workflowitems": len(paren)}
    return {"uitkomst": ONBEPAALD, "afgehandeld": None, "zekerheid": "laag",
            "uitleg": "GetWorkflow bevat geen herkenbare document-ID-velden; het antwoordformaat is niet gedocumenteerd. Verifieer in de interface.",
            "workflowitems": len(paren)}
