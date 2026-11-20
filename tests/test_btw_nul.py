"""Btw-bedrag 0 of ontbrekend: reden verplicht; bij verlegging/IC-verwerving bevestigen de gebruiker de btw-regels. Synthetische data."""
import json
from decimal import Decimal

import pytest

from yuki_mcp import boeking, dubbel

A = "[Vennootschapsnaam] BV"
SCHEMA = ("<ArrayOfGlAccount>" + "".join(f"<GlAccount><code>{c}</code><descriptionNL>R {c}</descriptionNL></GlAccount>"
                                          for c in ("440000", "400000", "411000", "451000", "613000", "700000", "499000")) + "</ArrayOfGlAccount>")
BASIS = {"type": "aankoop", "rekening": "613000", "btw_code": "0", "bedrag_incl": "100", "relatie": "[Voorbeeld] Lev", "datum": "2026-10-05", "omschrijving": "Dienst"}


def data(r):
    assert r["isError"] is False, r
    return json.loads(r["content"][0]["text"])


@pytest.fixture
def aan(monkeypatch, fake):
    monkeypatch.setattr(dubbel, "controleer", lambda h, regels, item, aanpass: {"uitkomst": dubbel.GEEN, "zekerheid": None, "redenen": [], "kandidaten": 0})
    monkeypatch.setenv("YUKI_WRITE_ENABLED", "ja")
    fake.responses["GetGLAccountScheme"] = SCHEMA
    fake.responses["ProcessJournal"] = "guid"
    return fake


def vraag(rpc, **extra):
    return data(rpc.call("yuki_boeking_voorstel", administratie=A, bron="wachtrekening", wachtrekening="499000", aanpassingen={**BASIS, **extra}))


def audit():
    p = boeking._dir() / "boekingen-audit.jsonl"
    return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []


def test_btw_nul_zonder_reden_geeft_geen_token(rpc, aan):
    r = vraag(rpc)
    assert r["voorstel"]["volledig"] is False and "bevestigingstoken" not in r
    assert any("btw_nul_reden" in x and "verlegd" in x and "intracommunautair" in x for x in r["voorstel"]["ontbrekend"])


def test_btw_bedrag_nul_of_ontbrekend_via_document_ook(rpc, aan):
    r = vraag(rpc, btw_code="21", btw_bedrag="0")
    assert r["voorstel"]["volledig"] is False and "bevestigingstoken" not in r


def test_ongeldige_reden_geweigerd(rpc, aan):
    assert "bevestigingstoken" not in vraag(rpc, btw_nul_reden="gewoon zo")


def test_reden_ander_vereist_toelichting(rpc, aan):
    r = vraag(rpc, btw_nul_reden="ander")
    assert "bevestigingstoken" not in r and any("btw_nul_toelichting" in x for x in r["voorstel"]["ontbrekend"])
    r = vraag(rpc, btw_nul_reden="ander", btw_nul_toelichting="abc")
    assert "bevestigingstoken" not in r
    r = vraag(rpc, btw_nul_reden="ander", btw_nul_toelichting="Subsidie zonder btw")
    assert r["bevestigingstoken"] and r["voorstel"]["btw_nul"]["toelichting"] == "Subsidie zonder btw"


@pytest.mark.parametrize("reden,label", [("vrijgesteld", "vrijgesteld"), ("buiten_toepassingsgebied", "buiten toepassingsgebied"),
                                          ("kleine_onderneming", "kleine onderneming/vrijstellingsregeling"), ("prive_niet_aftrekbaar", "privé of niet-aftrekbaar"),
                                          ("vrijgesteld", "vrijgesteld")])
def test_reden_zonder_btw_gevolgen_geeft_token_met_reden_in_omschrijving_en_audit(rpc, aan, reden, label):
    r = vraag(rpc, btw_nul_reden=reden)
    assert r["bevestigingstoken"] and label in r["voorstel"]["btw"]["nul_reden"]
    assert any("verifieer actuele regel" in w for w in r["voorstel"]["waarschuwingen"])
    rl = [x for x in r["voorstel"]["boekingsregels"] if x["relatie"]][0]
    assert f"[btw 0: {label}" in rl["omschrijving"] and f"[btw 0: {label}" in r["voorstel"]["journal_xml_dry_run"]
    assert [x["rekening"] for x in r["voorstel"]["boekingsregels"]] == ["613000", "440000"]       # niets automatisch toegevoegd
    ok = data(rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja"))
    assert ok["geboekt"] is True
    assert audit()[-1]["btw_nul"]["label"] == label and audit()[0]["btw_nul"]["label"] == label


def test_verlegd_en_ic_vereisen_bevestiging_en_waarschuwen(rpc, aan):
    for reden, woord in (("verlegd", "verlegd"), ("intracommunautair", "intracommunautaire")):
        r = vraag(rpc, btw_nul_reden=reden)
        assert "bevestigingstoken" not in r and any("btw_regels_bevestigd" in x for x in r["voorstel"]["ontbrekend"])
        assert any(woord in w and "verschuldigd" in w and "aftrekbaar" in w and "verifieer actuele regel" in w for w in r["voorstel"]["waarschuwingen"])
        assert any("niets automatisch" in x for x in r["voorstel"]["ontbrekend"])
        # bevestigd zonder extra regels: toegestaan (bewuste keuze), er wordt niets verzonnen
        r = vraag(rpc, btw_nul_reden=reden, btw_regels_bevestigd=True)
        assert r["bevestigingstoken"] and [x["rekening"] for x in r["voorstel"]["boekingsregels"]] == ["613000", "440000"]
        assert r["voorstel"]["btw_nul"]["btw_regels_bevestigd"] is True


def test_verlegd_met_door_gebruiker_aangevulde_btw_regels(rpc, aan):
    extra = [{"rekening": "411000", "bedrag": "21.00", "omschrijving": "btw verlegd aftrek"}, {"rekening": "451000", "bedrag": "-21.00", "omschrijving": "btw verlegd verschuldigd"}]
    r = vraag(rpc, btw_nul_reden="verlegd", btw_regels_bevestigd=True, btw_extra_regels=extra)
    regels = [(x["rekening"], x["bedrag"]) for x in r["voorstel"]["boekingsregels"]]
    assert regels == [("613000", 100.0), ("440000", -100.0), ("411000", 21.0), ("451000", -21.0)]
    assert sum(Decimal(str(b)) for _, b in regels) == 0 and r["bevestigingstoken"]
    # onevenwichtig, onbekende rekening, ongeldig
    assert "bevestigingstoken" not in vraag(rpc, btw_nul_reden="verlegd", btw_regels_bevestigd=True, btw_extra_regels=[extra[0]])
    bad = vraag(rpc, btw_nul_reden="verlegd", btw_regels_bevestigd=True, btw_extra_regels=[{"rekening": "999999", "bedrag": "5"}, {"rekening": "451000", "bedrag": "-5"}])
    assert "bevestigingstoken" not in bad and bad["voorstel"]["rekening_onbekend"] == ["999999"]
    assert "bevestigingstoken" not in vraag(rpc, btw_nul_reden="verlegd", btw_regels_bevestigd=True, btw_extra_regels=["x"])


def test_btw_nul_geldt_ook_voor_verkoop_maar_niet_voor_bank_of_gewone_btw(rpc, aan):
    r = vraag(rpc, type="verkoop", rekening="700000", btw_code="0")
    assert "bevestigingstoken" not in r
    r = vraag(rpc, btw_code="21", bedrag_incl="121")
    assert r["bevestigingstoken"] and r["voorstel"]["btw_nul"] is None
    r = data(rpc.call("yuki_boeking_voorstel", administratie=A, bron="wachtrekening", wachtrekening="499000",
                      aanpassingen={"rekening": "400000", "relatie": "[Klant A]"}))
    assert r["bevestigingstoken"]
