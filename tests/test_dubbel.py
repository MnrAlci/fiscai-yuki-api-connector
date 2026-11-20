"""Controle op dubbele boekingen. Synthetische [Voorbeeld]-data; geen netwerk."""
import json
from datetime import date

import pytest
from conftest import fault

from yuki_mcp import boeking, dubbel

A = "[Vennootschapsnaam] BV"
SCHEMA = ("<ArrayOfGlAccount>" + "".join(f"<GlAccount><code>{c}</code><descriptionNL>Rekening {c}</descriptionNL></GlAccount>"
                                          for c in ("440000", "400000", "411000", "613000")) + "</ArrayOfGlAccount>")
DOC = ("<ArrayOfDocument><Document ID='doc-1'><Subject>Factuur</Subject><DocumentDate>2026-10-05T00:00:00</DocumentDate><Amount>121.00</Amount>"
       "<VATAmount>21.00</VATAmount><Reference>LF-2026-001</Reference><ContactName>[Voorbeeld] Lev</ContactName></Document></ArrayOfDocument>")
AANP = {"type": "aankoop", "rekening": "613000", "btw_code": "21"}


def tx(bedrag, contact="[Voorbeeld] Lev", datum="2026-10-05", ref="", omschr="Inkoop", tid="x1"):
    return (f"<TransactionInfo><id>{tid}</id><transactionDate>{datum}T00:00:00</transactionDate><description>{omschr}</description>"
            f"<transactionAmount>{bedrag}</transactionAmount><glAccountCode>440000</glAccountCode><fullName>{contact}</fullName>"
            f"<documentReference>{ref}</documentReference></TransactionInfo>")


def data(r):
    assert r["isError"] is False, r
    return json.loads(r["content"][0]["text"])


@pytest.fixture
def echt(monkeypatch, fake):
    monkeypatch.setenv("YUKI_WRITE_ENABLED", "ja")
    fake.responses["GetGLAccountScheme"] = SCHEMA
    fake.responses["DocumentsInFolder"] = DOC
    fake.responses["ProcessJournal"] = "guid"

    def zet(*txs):
        fake.responses["GetTransactionDetails"] = "<ArrayOfTransactionInfo>" + "".join(txs) + "</ArrayOfTransactionInfo>"
    zet()
    fake.zet = zet
    return fake


def vraag(rpc, **extra):
    return data(rpc.call("yuki_boeking_voorstel", administratie=A, bron="documentworkflow", map_id=1, aanpassingen=AANP, **extra))


def audit():
    p = boeking._dir() / "boekingen-audit.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_geen_match_geeft_token(rpc, echt):
    echt.zet(tx("-77.00", contact="[Voorbeeld] Andere", datum="2026-09-20", ref="ZZ-9"))
    r = vraag(rpc)
    assert r["dubbelcontrole"]["uitkomst"] == dubbel.GEEN and "bevestigingstoken" not in r and r["workflow_geblokkeerd"] is True   # workflowdocument: nooit een token
    assert r["dubbelcontrole"]["methode"] == "AccountingInfo.GetTransactionDetails" and r["dubbelcontrole"]["venster"] == "2026-08-01 tot 2026-11-30"


def test_exacte_match_is_al_geboekt_en_geblokkeerd(rpc, echt):
    echt.zet(tx("-121.00"))
    r = vraag(rpc)
    assert r["dubbelcontrole"]["uitkomst"] == dubbel.AL and r["dubbelcontrole"]["zekerheid"] == "hoog"
    assert r["geblokkeerd"] is True and "bevestigingstoken" not in r and "voorstel_hash" not in r
    assert [x["uitkomst"] for x in audit()] == ["geblokkeerd"]


def test_match_op_referentie_met_ander_contact_en_datum(rpc, echt):
    echt.zet(tx("-121.00", contact="[Voorbeeld] Ander", datum="2026-10-20", ref="LF-2026-001"))
    r = vraag(rpc)
    assert r["dubbelcontrole"]["uitkomst"] == dubbel.AL and "referentie" in r["dubbelcontrole"]["redenen"][0] and "bevestigingstoken" not in r


def test_referentie_in_omschrijving_met_ander_bedrag_is_laag(rpc, echt):
    echt.zet(tx("-99.00", contact="[Voorbeeld] Ander", datum="2026-10-20", omschr="betaling LF-2026-001"))      # referentie in omschrijving, ander bedrag
    r = vraag(rpc)
    assert r["dubbelcontrole"]["uitkomst"] == dubbel.MOGELIJK and r["dubbelcontrole"]["zekerheid"] == "laag" and "bevestigingstoken" not in r


def test_tegengesteld_teken_is_mogelijk_al_geboekt(rpc, echt):
    echt.zet(tx("121.00", datum="2026-10-30"))
    r = vraag(rpc)
    assert r["dubbelcontrole"]["uitkomst"] == dubbel.MOGELIJK and "tegengesteld teken" in r["dubbelcontrole"]["redenen"][0]
    assert r["geblokkeerd"] is True and "bevestigingstoken" not in r


def test_zelfde_bedrag_en_relatie_andere_datum_is_mogelijk(rpc, echt):
    echt.zet(tx("-121.00", datum="2026-09-01"))
    r = vraag(rpc)
    assert r["dubbelcontrole"]["uitkomst"] == dubbel.MOGELIJK and r["dubbelcontrole"]["zekerheid"] == "midden" and "bevestigingstoken" not in r


def test_document_al_gekoppeld_aan_transactie(rpc, echt):
    echt.zet(tx("-5.00", contact="[Voorbeeld] Ander", ref="doc-1"))
    r = vraag(rpc)
    assert r["dubbelcontrole"]["uitkomst"] == dubbel.AL and "gekoppeld" in r["dubbelcontrole"]["redenen"][0]


def test_controle_mislukt_blokkeert(rpc, echt):
    echt.responses["GetTransactionDetails"] = fault("limiet of fout")
    r = vraag(rpc)
    assert r["dubbelcontrole"]["uitkomst"] == dubbel.MISLUKT and r["geblokkeerd"] is True and "bevestigingstoken" not in r
    assert "mislukt" in r["dubbelcontrole"]["redenen"][0]


def test_deblokkeren_vereist_expliciete_parameter_en_reden(rpc, echt):
    echt.zet(tx("-121.00"))
    for extra in ({"deblokkeer_reden": "dit is een geldige reden"}, {"deblokkeren": True}, {"deblokkeren": True, "deblokkeer_reden": "kort"},
                  {"deblokkeren": "ja", "deblokkeer_reden": "dit is een geldige reden"}):
        r = vraag(rpc, **extra)
        assert r["geblokkeerd"] is True and "bevestigingstoken" not in r, extra
    r = vraag(rpc, deblokkeren=True, deblokkeer_reden="Tweede factuur met zelfde bedrag, controle gedaan")
    assert "bevestigingstoken" not in r and r["workflow_geblokkeerd"] is True and r["gedeblokkeerd"]["reden"].startswith("Tweede factuur") and r["dubbelcontrole"]["uitkomst"] == dubbel.AL
    ev = audit()
    gd = [x for x in ev if x["uitkomst"] == "gedeblokkeerd"][-1]
    assert gd["reden"].startswith("Tweede factuur") and gd["dubbelcontrole"] == dubbel.AL
    assert "test-access-key-not-real" not in json.dumps(ev)
    assert [m for m in echt.methods() if m == "ProcessJournal"] == []


def test_beoordeel_en_venster_zuiver():
    rl = {"rekening": "440000", "bedrag": -121.0, "datum": "2026-10-05", "relatie": "[Voorbeeld] Lev"}
    assert dubbel.beoordeel(rl, {"id": "D:abc"}, {}, [])["uitkomst"] == dubbel.GEEN
    assert dubbel.venster(date(2026, 1, 10)) == (date(2025, 11, 1), date(2026, 2, 28))
    assert dubbel.blokkeert(dubbel.MISLUKT) and dubbel.blokkeert(dubbel.MOGELIJK) and not dubbel.blokkeert(dubbel.GEEN)


def test_controle_gebruikt_een_enkele_leescall_en_cache(rpc, echt):
    echt.zet(tx("-77.00", contact="[Voorbeeld] Andere"))
    vraag(rpc)
    n = [m for m in echt.methods() if m == "GetTransactionDetails"]
    assert len(n) == 1
    vraag(rpc)
    assert len([m for m in echt.methods() if m == "GetTransactionDetails"]) == 1    # tweede keer uit de cache
