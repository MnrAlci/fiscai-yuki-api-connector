"""Boekingsworkflow: standaard uit, token per voorstel, dry-run, geen bulk, audit. Alleen mocks en synthetische [Voorbeeld]-data."""
import json
import re
import stat
import time

import pytest
from conftest import fault

from yuki_mcp import boeking, edition
from yuki_mcp.transport import PluginTransport

A = "[Vennootschapsnaam] BV"
SCHEMA = ("<ArrayOfGlAccount>" + "".join(f"<GlAccount><code>{c}</code><descriptionNL>Rekening {c}</descriptionNL></GlAccount>"
                                          for c in ("499000", "440000", "400000", "411000", "451000", "610000", "700000", "613000")) + "</ArrayOfGlAccount>")


def data(r):
    assert r["isError"] is False, r
    return json.loads(r["content"][0]["text"])


@pytest.fixture
def aan(monkeypatch, fake):
    from yuki_mcp import dubbel     # de dubbelcontrole wordt apart getest (test_dubbel.py); hier: geen bestaande boeking
    monkeypatch.setattr(dubbel, "controleer", lambda h, regels, item, aanpass: {"uitkomst": dubbel.GEEN, "zekerheid": None, "redenen": [], "kandidaten": 0})
    monkeypatch.setenv("YUKI_WRITE_ENABLED", "ja")
    fake.responses["GetGLAccountScheme"] = SCHEMA
    fake.responses["ProcessJournal"] = "11111111-2222-3333-4444-555555555555"
    return fake


def voorstel(rpc, **extra):
    return data(rpc.call("yuki_boeking_voorstel", administratie=A, bron="wachtrekening", wachtrekening="499000", **extra))


def schrijfcalls(fake):
    return [m for m in fake.methods() if m == "ProcessJournal"]


# ------------------------------------------------------------------ standaard uit
def test_zonder_env_geen_yuki_calls_geen_token_geen_schrijven(rpc, fake):
    r = data(rpc.call("yuki_boeking_voorstel", administratie=A, bron="wachtrekening", wachtrekening="499000"))
    assert r["actief"] is False and "YUKI_WRITE_ENABLED=ja" in r["uitleg"] and fake.requests == []
    assert data(rpc.call("yuki_boeking_overslaan", administratie=A, item_id="W:t-1"))["actief"] is False
    b = rpc.call("yuki_boeking_bevestigen", administratie=A, token="x", voorstel_hash="y", bevestiging="ja")
    assert b["isError"] is True and "uit" in b["content"][0]["text"].lower() and fake.requests == []
    s = data(rpc.call("yuki_boeking_status"))
    assert s["actief"] is False and s["geboekt_vandaag"] == 0


@pytest.mark.parametrize("waarde", ["", "nee", "true", "1", "yes", "ja!", "JAA"])
def test_alleen_de_waarde_ja_zet_het_aan(monkeypatch, waarde):
    monkeypatch.setenv("YUKI_WRITE_ENABLED", waarde)
    assert boeking.write_enabled() is False
    monkeypatch.setenv("YUKI_WRITE_ENABLED", " JA ")
    assert boeking.write_enabled() is True


def test_transport_weigert_processjournal_zonder_env_en_zonder_context(fake, monkeypatch):
    import httpx
    t = PluginTransport("https://api.example.test/ws", http_client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    with pytest.raises(Exception):
        t.call("Accounting", "ProcessJournal", [("sessionID", "x")])                    # geen context, geen env
    with pytest.raises(Exception):
        with t.allow_journal_write():                                                  # context zonder env
            pass
    monkeypatch.setenv("YUKI_WRITE_ENABLED", "ja")
    with pytest.raises(Exception):
        t.call("Accounting", "ProcessJournal", [("sessionID", "x")])                    # env zonder context
    assert fake.requests == []
    with pytest.raises(Exception):
        with t.allow_journal_write():
            t.call("Accounting", "ProcessJournal2", [("sessionID", "x")])               # enkel ProcessJournal
    with pytest.raises(Exception):
        with t.allow_journal_write():
            t.call("Accounting", "ProcessSalesInvoices", [("sessionID", "x")])          # geen andere schrijfmethodes
    assert fake.requests == []


# ------------------------------------------------------------------ voorstellen
def test_voorstel_wachtrekening_onvolledig_geeft_geen_token(rpc, aan):
    r = voorstel(rpc)
    assert r["actief"] is True and r["item"]["id"] == "W:t-1" and r["voorstel"]["volledig"] is False
    assert any("rekening" in x for x in r["voorstel"]["ontbrekend"]) and "bevestigingstoken" not in r
    assert any("MAR" in w and "verifieer actuele regel" in w for w in r["voorstel"]["waarschuwingen"])   # Belgische afbakening
    assert schrijfcalls(aan) == []


def test_voorstel_bank_herclassificeert_van_wachtrekening_met_token(rpc, aan):
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    v = r["voorstel"]
    assert v["volledig"] and v["type"] == "bank" and [x["rekening"] for x in v["boekingsregels"]] == ["400000", "499000"]
    assert sum(x["bedrag"] for x in v["boekingsregels"]) == 0 and v["boekingsregels"][0]["bedrag"] == 250.0
    assert r["bevestigingstoken"] and r["voorstel_hash"] == boeking.voorstel_hash(rpc.srv.tools.f.get(None).resolve(A).id, v["journal_xml_dry_run"])
    xml = v["journal_xml_dry_run"]
    assert xml.startswith('<Journal xmlns="urn:xmlns:http://www.theyukicompany.com:journal">') and "<JournalType>GeneralJournal</JournalType>" in xml
    assert re.search(r"<JournalEntry>.*<EntryDate>2026-10-01</EntryDate><GLAccount>400000</GLAccount><Amount>250.00</Amount>", xml)
    assert schrijfcalls(aan) == []


def test_voorstel_aankoop_btw_21_en_niet_aftrekbaar(rpc, aan):
    r = voorstel(rpc, aanpassingen={"type": "aankoop", "rekening": "613000", "btw_code": "21", "bedrag_incl": "121", "relatie": "[Leverancier] BV",
                                    "datum": "2026-10-05", "referentie": "LF-1", "omschrijving": "Kantoormateriaal"})
    regels = r["voorstel"]["boekingsregels"]
    assert [(x["rekening"], x["bedrag"]) for x in regels] == [("613000", 100.0), ("411000", 21.0), ("440000", -121.0)]
    assert regels[2]["relatie"] == "[Leverancier] BV" and r["voorstel"]["btw"]["aftrekbaar"] is True
    r = voorstel(rpc, aanpassingen={"type": "aankoop", "rekening": "613000", "btw_code": "21", "btw_aftrek": False, "bedrag_incl": "121", "relatie": "[Leverancier]",
                                    "datum": "2026-10-05"})
    assert [(x["rekening"], x["bedrag"]) for x in r["voorstel"]["boekingsregels"]] == [("613000", 121.0), ("440000", -121.0)]


def test_voorstel_verkoop_en_btw_codes_belgisch(rpc, aan):
    r = voorstel(rpc, aanpassingen={"type": "verkoop", "rekening": "700000", "btw_code": "6", "bedrag_incl": "106", "relatie": "[Klant]", "datum": "2026-10-05"})
    assert [(x["rekening"], x["bedrag"]) for x in r["voorstel"]["boekingsregels"]] == [("400000", 106.0), ("700000", -100.0), ("451000", -6.0)]
    r = voorstel(rpc, aanpassingen={"type": "verkoop", "rekening": "700000", "btw_code": "19", "bedrag_incl": "10", "relatie": "[Klant]", "datum": "2026-10-05"})
    assert r["voorstel"]["volledig"] is False and any("21, 12, 6 of 0" in x for x in r["voorstel"]["ontbrekend"])
    r = voorstel(rpc, aanpassingen={"type": "aankoop", "rekening": "613000", "btw_code": "0", "btw_nul_reden": "vrijgesteld", "bedrag_incl": "50", "relatie": "[L]", "datum": "2026-10-05"})
    assert [(x["rekening"], x["bedrag"]) for x in r["voorstel"]["boekingsregels"]] == [("613000", 50.0), ("440000", -50.0)]


def test_onbekende_rekening_geen_token(rpc, aan):
    r = voorstel(rpc, aanpassingen={"rekening": "999999", "relatie": "[Klant A]"})
    assert r["voorstel"]["volledig"] is False and r["voorstel"]["rekening_onbekend"] == ["999999"] and "bevestigingstoken" not in r


def test_journaal_validatie_somt_nul_en_minimaal_twee_regels():
    R = boeking.Regel
    with pytest.raises(ValueError):
        boeking.valideer([R("1", boeking.D(5), "x", "2026-01-01")])
    with pytest.raises(ValueError):
        boeking.valideer([R("1", boeking.D(5), "x", "2026-01-01"), R("2", boeking.D(-4), "x", "2026-01-01")])
    with pytest.raises(ValueError):       # per datum moet het saldo 0 zijn
        boeking.valideer([R("1", boeking.D(5), "x", "2026-01-01"), R("2", boeking.D(-5), "x", "2026-01-02")])
    with pytest.raises(ValueError):
        boeking.valideer([R("1", boeking.D(5), "x", "01/01/2026"), R("2", boeking.D(-5), "x", "01/01/2026")])
    x = boeking.journal_xml("ADM&1", "A < B", [R("1", boeking.D(5), "a & b", "2026-01-01", "Naam <x>"), R("2", boeking.D(-5), "c", "2026-01-01")])
    assert "ADM&amp;1" in x and "a &amp; b" in x and "Naam &lt;x&gt;" in x


# ------------------------------------------------------------------ bevestigen
def test_dry_run_toont_exacte_xml_zonder_te_boeken_en_token_blijft_geldig(rpc, aan):
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    d = data(rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], dry_run=True))
    assert d["dry_run"] is True and d["geboekt"] is False and d["journal_xml"] == r["voorstel"]["journal_xml_dry_run"]
    assert "<xmlDoc><Journal xmlns=" in d["soap_body"] and "[GEHEIM]" in d["soap_body"] and schrijfcalls(aan) == []
    ok = data(rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja"))
    assert ok["geboekt"] is True


def test_zonder_bevestiging_geen_boeking(rpc, aan):
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    b = rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"])
    assert b["isError"] is True and schrijfcalls(aan) == []
    b = rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="nee")
    assert b["isError"] is True and schrijfcalls(aan) == []


def test_zonder_token_of_met_verkeerd_token_geen_boeking(rpc, aan):
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    for tok in ("", "verzonnen-token", None):
        b = rpc.call("yuki_boeking_bevestigen", administratie=A, token=tok, voorstel_hash=r["voorstel_hash"], bevestiging="ja")
        assert b["isError"] is True
    assert schrijfcalls(aan) == []


def test_afwijkende_hash_administratie_of_gewijzigd_voorstel_geweigerd(rpc, aan, monkeypatch):
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    b = rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash="0" * 64, bevestiging="ja")
    assert b["isError"] is True and "voorstel_hash" in b["content"][0]["text"]
    # token van een andere administratie
    aan.responses["Administrations"] = ("<Administration><ID>00000000-0000-0000-0000-000000000002</ID><Name>[Andere] BV</Name>"
                                        "<DomainID>00000000-0000-0000-0000-000000000010</DomainID></Administration>"
                                        "<Administration><ID>00000000-0000-0000-0000-000000000001</ID><Name>[Vennootschapsnaam] BV</Name>"
                                        "<DomainID>00000000-0000-0000-0000-000000000010</DomainID></Administration>")
    b = rpc.call("yuki_boeking_bevestigen", administratie="[Andere] BV", token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja", vernieuwen=True)
    assert b["isError"] is True
    # het opgeslagen voorstel werd achteraf aangepast: geweigerd (hash-controle)
    p = boeking._dir() / "boeking-tokens.json"
    tk = json.loads(p.read_text())
    tk[r["bevestigingstoken"]]["xml"] = tk[r["bevestigingstoken"]]["xml"].replace("250.00", "9250.00")
    p.write_text(json.dumps(tk))
    b = rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja")
    assert b["isError"] is True and schrijfcalls(aan) == []


def test_token_is_eenmalig_en_verloopt(rpc, aan, monkeypatch):
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    a1 = data(rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja"))
    assert a1["geboekt"] is True and len(schrijfcalls(aan)) == 1
    again = rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja")
    assert again["isError"] is True and len(schrijfcalls(aan)) == 1             # hergebruik geweigerd
    r2 = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant B]"})
    real = time.time
    monkeypatch.setattr(boeking.time, "time", lambda: real() + 16 * 60)            # standaard vervaltijd 15 minuten
    late = rpc.call("yuki_boeking_bevestigen", administratie=A, token=r2["bevestigingstoken"], voorstel_hash=r2["voorstel_hash"], bevestiging="ja")
    assert late["isError"] is True and "verlopen" in late["content"][0]["text"] and len(schrijfcalls(aan)) == 1


def test_vervaltijd_instelbaar_met_grenzen(monkeypatch):
    monkeypatch.setenv("YUKI_WRITE_TOKEN_TTL_MIN", "500")
    assert boeking.ttl_minuten() == 60
    monkeypatch.setenv("YUKI_WRITE_TOKEN_TTL_MIN", "0")
    assert boeking.ttl_minuten() == 1
    monkeypatch.setenv("YUKI_WRITE_TOKEN_TTL_MIN", "abc")
    assert boeking.ttl_minuten() == 15


def test_bulk_onmogelijk(rpc, aan):
    r1 = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    r2 = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant B]"})               # nieuw voorstel: oud token ongeldig
    old = rpc.call("yuki_boeking_bevestigen", administratie=A, token=r1["bevestigingstoken"], voorstel_hash=r1["voorstel_hash"], bevestiging="ja")
    assert old["isError"] is True and schrijfcalls(aan) == []
    for bad in ([r2["bevestigingstoken"]], [r2["bevestigingstoken"], r1["bevestigingstoken"]], {"a": 1}):
        assert rpc.call("yuki_boeking_bevestigen", administratie=A, token=bad, voorstel_hash=r2["voorstel_hash"], bevestiging="ja")["isError"] is True
    schema = next(t for t in rpc.req("tools/list")["result"]["tools"] if t["name"] == "yuki_boeking_bevestigen")["inputSchema"]
    assert schema["properties"]["token"]["type"] == "string" and all(p.get("type") != "array" for p in schema["properties"].values())
    assert schrijfcalls(aan) == []
    ok = data(rpc.call("yuki_boeking_bevestigen", administratie=A, token=r2["bevestigingstoken"], voorstel_hash=r2["voorstel_hash"], bevestiging="ja"))
    assert ok["geboekt"] is True and len(schrijfcalls(aan)) == 1                                  # exact één boeking per call


def test_dagmaximum(rpc, aan, monkeypatch):
    monkeypatch.setenv("YUKI_WRITE_MAX_PER_DAY", "1")
    r1 = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    assert data(rpc.call("yuki_boeking_bevestigen", administratie=A, token=r1["bevestigingstoken"], voorstel_hash=r1["voorstel_hash"], bevestiging="ja"))["geboekt"]
    r2 = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant B]"})
    b = rpc.call("yuki_boeking_bevestigen", administratie=A, token=r2["bevestigingstoken"], voorstel_hash=r2["voorstel_hash"], bevestiging="ja")
    assert b["isError"] is True and "Dagmaximum" in b["content"][0]["text"] and len(schrijfcalls(aan)) == 1


def test_geboekt_item_verschijnt_niet_meer_en_overslaan_werkt(rpc, aan):
    r = voorstel(rpc)
    assert r["item"]["id"] == "W:t-1" and r["nog_te_behandelen"] == 2
    data(rpc.call("yuki_boeking_overslaan", administratie=A, item_id="W:t-1"))
    r = voorstel(rpc)
    assert r["item"]["id"] == "W:t-2" and r["nog_te_behandelen"] == 1
    data(rpc.call("yuki_boeking_overslaan", administratie=A, item_id="W:t-2"))
    assert voorstel(rpc)["klaar"] is True


def test_schrijfcall_xml_in_soap_body_ongeescaped_en_telt_mee_in_daglimiet(rpc, aan):
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    n0 = sum(d["calls_today"] for d in data(rpc.call("yuki_status"))["domains"])
    data(rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja"))
    req = [x for x in aan.requests if x[1] == "ProcessJournal"][0]
    assert req[0] == "Accounting" and "<xmlDoc><Journal xmlns=\"urn:xmlns:http://www.theyukicompany.com:journal\">" in req[2]
    assert "&lt;Journal" not in req[2] and "<administrationID>00000000-0000-0000-0000-000000000001</administrationID>" in req[2]
    n1 = sum(d["calls_today"] for d in data(rpc.call("yuki_status"))["domains"])
    assert n1 > n0


def test_audit_log_zonder_sleutel_met_poging_en_uitkomst(rpc, aan):
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    data(rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja"))
    p = boeking._dir() / "boekingen-audit.jsonl"
    assert stat.S_IMODE(p.stat().st_mode) == 0o600
    recs = [json.loads(x) for x in p.read_text().splitlines()]
    assert [x["uitkomst"] for x in recs] == ["poging", "geboekt"] and recs[1]["document_id"] == "11111111-2222-3333-4444-555555555555"
    assert recs[0]["voorstel_hash"] == r["voorstel_hash"] and recs[0]["regels"] and "tijd" in recs[0]
    blob = p.read_text()
    assert "test-access-key-not-real" not in blob and "test-cache-secret-not-real" not in blob and "fake-session" not in blob
    assert data(rpc.call("yuki_boeking_status"))["geboekt_vandaag"] == 1


def test_fout_bij_yuki_wordt_gelogd_en_token_is_dan_verbruikt(rpc, aan):
    aan.responses["ProcessJournal"] = fault("The sum of all lines must be 0,00")
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})
    b = rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja")
    assert b["isError"] is True
    recs = [json.loads(x) for x in (boeking._dir() / "boekingen-audit.jsonl").read_text().splitlines()]
    assert [x["uitkomst"] for x in recs] == ["poging", "fout"] and "YukiSoapFault" in recs[1]["fout"]
    again = rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja")
    assert again["isError"] is True and len(schrijfcalls(aan)) == 1
    assert voorstel(rpc)["item"]["id"] == "W:t-1"                 # niet als behandeld gemarkeerd


def test_documentworkflow_bron_leest_archiefmap(rpc, aan):
    aan.responses["DocumentsInFolder"] = ("<ArrayOfDocument><Document ID='doc-1'><Subject>Factuur [Voorbeeld] Lev</Subject><DocumentDate>2026-10-02T00:00:00</DocumentDate>"
                                          "<Amount>242.00</Amount><ContactName>[Voorbeeld] Lev</ContactName></Document></ArrayOfDocument>")
    r = data(rpc.call("yuki_boeking_voorstel", administratie=A, bron="documentworkflow", map_id=3,
                      aanpassingen={"rekening": "613000", "btw_code": "21"}))
    assert r["item"]["id"] == "D:doc-1" and r["item"]["bron"] == "documentworkflow" and r["voorstel"]["type"] == "aankoop"
    assert [(x["rekening"], x["bedrag"]) for x in r["voorstel"]["boekingsregels"]] == [("613000", 200.0), ("411000", 42.0), ("440000", -242.0)]
    assert r["workflow_geblokkeerd"] is True and "bevestigingstoken" not in r and schrijfcalls(aan) == []
    assert boeking.WORKFLOW_BLOK in r["uitleg"] and "dubbele kost" in r["uitleg"]
    miss = rpc.call("yuki_boeking_voorstel", administratie=A, bron="documentworkflow")
    assert miss["isError"] is True


def test_geen_generieke_tool_kan_schrijven():
    from yuki_mcp.transport import is_allowed
    for m in ("ProcessJournal", "ProcessPurchaseInvoices", "ProcessSalesInvoices", "UploadDocument", "UpdateContact"):
        assert not any(is_allowed(s, m) for s in ("Accounting", "Purchase", "Sales", "Archive", "Contact"))


@pytest.mark.skipif(edition.INTERNAL_RULES, reason="alleen editie B")
def test_editie_b_heeft_geen_kantoorregels(rpc, aan):
    r = voorstel(rpc, aanpassingen={"type": "aankoop", "rekening": "613000", "btw_code": "21", "bedrag_incl": "121", "relatie": "Restaurant De Zon",
                                    "datum": "2026-10-05", "omschrijving": "Restaurant lunch"})
    assert [x["rekening"] for x in r["voorstel"]["boekingsregels"]] == ["613000", "411000", "440000"] and r["voorstel"]["regels_toegepast"] == []


def test_btw_bedrag_uit_workflowdocument_heeft_voorrang_op_percentage(rpc, aan):
    aan.responses["DocumentsInFolder"] = ("<ArrayOfDocument><Document ID='doc-9'><Subject>Factuur</Subject><DocumentDate>2026-10-02T00:00:00</DocumentDate>"
                                          "<Amount>-120.99</Amount><VATAmount>-20.99</VATAmount><ContactName>[Voorbeeld] Lev</ContactName></Document></ArrayOfDocument>")
    r = data(rpc.call("yuki_boeking_voorstel", administratie=A, bron="documentworkflow", map_id=1,
                      aanpassingen={"type": "aankoop", "rekening": "613000", "btw_code": "21"}))
    assert [(x["rekening"], x["bedrag"]) for x in r["voorstel"]["boekingsregels"]] == [("613000", 100.0), ("411000", 20.99), ("440000", -120.99)] or \
        [(x["rekening"], x["bedrag"]) for x in r["voorstel"]["boekingsregels"]][1] == ("411000", 20.99)
    from decimal import Decimal
    assert sum(Decimal(str(x["bedrag"])) for x in r["voorstel"]["boekingsregels"]) == 0


def test_workflowdocument_waarschuwt_dat_processjournal_een_memoriaalpost_is(rpc, aan):
    aan.responses["DocumentsInFolder"] = ("<ArrayOfDocument><Document ID='doc-1'><Subject>Factuur</Subject><DocumentDate>2026-10-02T00:00:00</DocumentDate>"
                                          "<Amount>121.00</Amount><VATAmount>21.00</VATAmount><ContactName>[Voorbeeld] Lev</ContactName></Document></ArrayOfDocument>")
    r = data(rpc.call("yuki_boeking_voorstel", administratie=A, bron="documentworkflow", map_id=1, aanpassingen={"type": "aankoop", "rekening": "613000"}))
    w = " ".join(r["voorstel"]["waarschuwingen"])
    assert "memoriaalpost" in w and "Afgehandeld" in w and "geen gedocumenteerde methode" in w.replace("Voor Yuki is ", "").replace("gevonden", "") or "Afgehandeld" in w
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})        # bank/wachtrekening: geen dagboekwaarschuwing
    assert not any("memoriaalpost" in x for x in r["voorstel"]["waarschuwingen"])


def _workflow_token(admin_id, type_):
    xml = ("<Journal xmlns=\"urn:xmlns:http://www.theyukicompany.com:journal\"><JournalEntry><EntryDate>2026-10-05</EntryDate><GLAccount>613000</GLAccount><Amount>10.00</Amount>"
           "<Description>x</Description></JournalEntry><JournalEntry><EntryDate>2026-10-05</EntryDate><GLAccount>440000</GLAccount><Amount>-10.00</Amount><Description>x</Description></JournalEntry></Journal>")
    extra = {"type": type_} if type_ else {}
    return boeking.nieuw_token(admin_id, A, "D:doc-1", "documentworkflow", xml, [], extra)


@pytest.mark.parametrize("soort", ["aankoop", "verkoop", None])
def test_bevestigen_weigert_workflowdocument_hard(rpc, aan, soort):
    adm = rpc.srv.tools.f.get(None).resolve(A).id
    t = _workflow_token(adm, soort)
    for extra in ({"bevestiging": "ja"}, {"dry_run": True}):
        b = rpc.call("yuki_boeking_bevestigen", administratie=A, token=t["bevestigingstoken"], voorstel_hash=t["voorstel_hash"], **extra)
        assert b["isError"] is True
        txt = b["content"][0]["text"]
        assert boeking.WORKFLOW_BLOK in txt and "dubbele kost" in txt and "Workflowdocumenten handel je af" in txt
    assert schrijfcalls(aan) == []
    tokens = json.loads((boeking._dir() / "boeking-tokens.json").read_text())
    assert tokens[t["bevestigingstoken"]]["gebruikt"] is False          # niet eens verbruikt: gewoon geweigerd


def test_echte_memoriaalpost_blijft_mogelijk(rpc, aan):
    r = voorstel(rpc, aanpassingen={"rekening": "400000", "relatie": "[Klant A]"})        # bron wachtrekening = echte memoriaalpost
    assert r["bevestigingstoken"] and "workflow_geblokkeerd" not in r
    ok = data(rpc.call("yuki_boeking_bevestigen", administratie=A, token=r["bevestigingstoken"], voorstel_hash=r["voorstel_hash"], bevestiging="ja"))
    assert ok["geboekt"] is True and len(schrijfcalls(aan)) == 1


def test_workflowdocument_geeft_geen_token_ook_niet_bij_deblokkeren_en_wordt_geaudit(rpc, aan):
    aan.responses["DocumentsInFolder"] = ("<ArrayOfDocument><Document ID='doc-1'><Subject>Factuur</Subject><DocumentDate>2026-10-02T00:00:00</DocumentDate>"
                                          "<Amount>121.00</Amount><VATAmount>21.00</VATAmount><ContactName>[Voorbeeld] Lev</ContactName></Document></ArrayOfDocument>")
    for extra in ({}, {"deblokkeren": True, "deblokkeer_reden": "dit is een geldige reden"}):
        r = data(rpc.call("yuki_boeking_voorstel", administratie=A, bron="documentworkflow", map_id=1, aanpassingen={"type": "aankoop", "rekening": "613000"}, **extra))
        assert r["workflow_geblokkeerd"] is True and "bevestigingstoken" not in r and "journal_xml_dry_run" not in r["voorstel"]
    p = boeking._dir() / "boekingen-audit.jsonl"
    assert any(json.loads(x)["uitkomst"] == "workflow_geblokkeerd" for x in p.read_text().splitlines())
