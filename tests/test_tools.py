import json
import re

import pytest
from conftest import ADMIN_1, FAKE_CACHE, FAKE_KEY, fault

from yuki_mcp import registry
from yuki_mcp.transport import ALLOWED, EXCLUDED_METHODS, PluginTransport, WRITE_PREFIXES, is_allowed

A = "[Vennootschapsnaam] BV"


def data(r):
    assert r["isError"] is False, r
    return json.loads(r["content"][0]["text"])


def test_initialize_en_tools_list(rpc):
    r = rpc.req("initialize")["result"]
    assert r["serverInfo"]["name"] and "tools" in r["capabilities"]
    tools = rpc.req("tools/list")["result"]["tools"]
    names = {t["name"] for t in tools}
    for n in ("yuki_status", "yuki_administraties", "yuki_proefbalans", "yuki_netto_omzet", "yuki_openstaande_posten",
              "yuki_grootboekmutaties", "yuki_jaartotalen", "yuki_dashboard", "yuki_herinneringsmail", "yuki_handleiding_saldi",
              "yuki_ouderdom_openstaande_posten", "yuki_dso_dpo", "yuki_periodevergelijking", "yuki_uitschieters",
              "yuki_archief_documenten", "yuki_contacten_zoeken", "yuki_btw_aangiftes"):
        assert n in names
    assert len(names) == len(tools) >= 50


LOKALE_TOOLS = {"yuki_opslag_status", "yuki_opslag_instellen", "yuki_boeking_status", "yuki_boeking_overslaan"}
BOEKING_TOOLS = {"yuki_boeking_voorstel", "yuki_boeking_overslaan", "yuki_boeking_bevestigen", "yuki_boeking_status"}


def test_alle_tools_alleen_lezen_met_hints_en_schema(rpc):
    for t in rpc.req("tools/list")["result"]["tools"]:
        a = t["annotations"]
        if t["name"] == "yuki_boeking_bevestigen":          # de enige schrijftool (standaard uit)
            assert a["readOnlyHint"] is False and a["destructiveHint"] is True and a["idempotentHint"] is False, t["name"]
        elif t["name"] == "yuki_boeking_voorstel":          # leest Yuki, schrijft alleen een lokaal token
            assert a["readOnlyHint"] is False and a["destructiveHint"] is False and a["openWorldHint"] is True
        elif t["name"] in LOKALE_TOOLS:      # enkel lokale configuratie, geen Yuki-call
            assert a["destructiveHint"] is False and a["openWorldHint"] is False, t["name"]
            assert a["readOnlyHint"] is (t["name"] in ("yuki_opslag_status", "yuki_boeking_status"))
        else:
            assert a["readOnlyHint"] is True and a["destructiveHint"] is False and a["openWorldHint"] is True, t["name"]
        assert t["title"] and len(t["description"]) > 20
        assert t["inputSchema"]["type"] == "object"
        assert not re.search(r"(?i)(schrijf|verstuur|verwijder|upload|process|update|delete|write|send)", t["name"])
        assert t["name"] in BOEKING_TOOLS or not t["name"].startswith("yuki_boeking")


def test_geen_enkele_tool_wijst_naar_schrijfmethode():
    for g in registry.GENERIC:
        for m in registry.all_methods(g):
            assert is_allowed(g.service, m), (g.tool, m)
            assert m not in EXCLUDED_METHODS and not m.startswith(WRITE_PREFIXES)


@pytest.mark.parametrize("service,method", [("Accounting", "ProcessJournal"), ("Sales", "ProcessSalesInvoices"),
                                            ("Purchase", "ProcessPurchaseInvoices"), ("Contact", "UpdateContact"),
                                            ("Archive", "UploadDocument"), ("Accounting", "SetCurrentDomain"),
                                            ("Archive", "DocumentBinaryData"), ("Accounting", "AuthenticateByUserName"),
                                            ("Onbekend", "Documents")])
def test_schrijf_en_binaire_methodes_geweigerd(service, method, fake):
    import httpx
    t = PluginTransport("https://api.example.test/ws", http_client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    with pytest.raises(Exception) as ei:
        t.call(service, method, [("sessionID", "x")])
    assert "toegelaten" in str(ei.value)
    assert fake.requests == []


def test_administraties_en_proefbalans_via_mock(rpc, fake):
    adm = data(rpc.call("yuki_administraties"))
    assert adm[0]["name"] == A
    tb = data(rpc.call("yuki_proefbalans", administratie=A, datum="2026-09-30"))
    assert {l["code"] for l in tb} == {"550000", "400000", "700000"}
    assert "GLAccountBalance" in fake.methods()


def test_quota_telling_via_tools_en_status(rpc, fake):
    rpc.call("yuki_administraties")
    rpc.call("yuki_proefbalans", administratie=A, datum="2026-09-30")
    st = data(rpc.call("yuki_status"))
    calls = sum(d["calls_today"] for d in st["domains"])
    assert calls == len(fake.requests) >= 3
    assert st["limit"] == 900 and "gratis" in st["gratis"]


def test_daglimiet_blokkeert_via_tool(server, fake, monkeypatch):
    from conftest import Rpc
    monkeypatch.setenv("YUKI_DAILY_LIMIT", "4")
    r = Rpc(server())
    r.call("yuki_administraties")                      # Authenticate + Administrations = 2
    outs = [r.call("yuki_proefbalans", administratie=A, datum=f"2026-09-{d:02d}", vernieuwen=True) for d in range(1, 9)]
    assert any(o["isError"] and "limit" in o["content"][0]["text"].lower() for o in outs)
    assert fake.methods().count("GLAccountBalance") == 4        # limiet 4 per domein: de 5e wordt niet verstuurd


def test_limiet_boven_1000_zonder_akkoord_begrensd_in_tool(server, monkeypatch):
    from conftest import Rpc
    monkeypatch.setenv("YUKI_DAILY_LIMIT", "5000")
    st = data(Rpc(server()).call("yuki_status"))
    assert st["limit"] == 1000 and st["waarschuwingen"]


def test_toegangsniveau(server, monkeypatch):
    from conftest import Rpc
    assert data(Rpc(server()).call("yuki_status"))["toegangsniveau"] == "portaal"
    monkeypatch.setenv("YUKI_ACCESS_LEVEL", "domein")
    assert data(Rpc(server()).call("yuki_status"))["toegangsniveau"] == "domein"
    monkeypatch.setenv("YUKI_ACCESS_LEVEL", "nonsens")
    with pytest.raises(Exception):
        server()
        from yuki_mcp.clientfactory import access_level
        access_level()


def test_paginering_record_en_page(rpc, fake):
    d = data(rpc.call("yuki_archief_documenten", administratie=A, paginagrootte=2))
    assert d["aantal"] == 3 and d["volledig"] is True and d["paginas"] == 2
    assert "administrationID" not in fake.requests[-1][2]      # domeinniveau
    d2 = data(rpc.call("yuki_archief_documenten", administratie=A, paginagrootte=2, max_paginas=1, vernieuwen=True))
    assert d2["volledig"] is False and d2["reden_onvolledig"] == "max_paginas bereikt" and d2["aantal"] == 2
    c = data(rpc.call("yuki_contacten_zoeken", administratie=A, zoekoptie="All"))
    assert c["aantal"] == 3 and c["volledig"] is True


def test_admin_scope_stuurt_administration_id(rpc, fake):
    rpc.call("yuki_rekeningschema", administratie=A)
    r = rpc.call("yuki_startbalans", administratie=A, boekjaar=2026)
    assert fake.requests[-1][1] == "GetStartBalanceByGlAccount"
    assert ADMIN_1 in fake.requests[-1][2]


def test_ontbrekende_verplichte_parameter_is_toolfout(rpc):
    r = rpc.call("yuki_startbalans", administratie=A)
    assert r["isError"] is True


def test_geen_geheimen_in_uitvoer_of_fouten(rpc, fake):
    fake.responses["GLAccountBalance"] = fault(f"boem {FAKE_KEY} en {FAKE_CACHE}")
    outs = [rpc.call("yuki_administraties"), rpc.call("yuki_status"),
            rpc.call("yuki_proefbalans", administratie=A, datum="2026-09-30"), rpc.call("yuki_openstaande_posten", administratie=A, soort="debiteuren")]
    blob = json.dumps(outs)
    assert FAKE_KEY not in blob and FAKE_CACHE not in blob and "fake-session" not in blob
    assert "[GEHEIM]" in blob


def test_creditor_sign_normalisatie(server, fake, monkeypatch):
    from conftest import Rpc
    r = Rpc(server())
    pos = data(r.call("yuki_ouderdom_openstaande_posten", administratie=A, soort="crediteuren", peildatum="2026-11-30"))
    assert pos["negatieve_posten"]["bedrag"] == -350.0           # fixture: negatieve open bedragen
    monkeypatch.setenv("YUKI_CREDITOR_SIGN", "negatief")
    r2 = Rpc(server())
    neg = data(r2.call("yuki_ouderdom_openstaande_posten", administratie=A, soort="crediteuren", peildatum="2026-11-30", vernieuwen=True))
    assert neg["totaal_positief"] == 350.0


def test_alias_sleutel_en_automatische_cachesleutel(server, fake, monkeypatch, tmp_path):
    from conftest import Rpc
    monkeypatch.delenv("YUKI_ACCESS_KEY")
    monkeypatch.delenv("YUKI_CACHE_KEY")
    monkeypatch.setenv("YUKI_API_KEY", "alias-key-not-real")
    r = Rpc(server())
    assert data(r.call("yuki_administraties"))
    kf = tmp_path / "secrets" / "cache.key"
    assert kf.exists() and (kf.stat().st_mode & 0o777) == 0o600
    assert "alias-key-not-real" not in json.dumps(r.call("yuki_status"))
    monkeypatch.delenv("YUKI_API_KEY")
    r2 = Rpc(server())
    assert r2.call("yuki_administraties")["isError"] is True


def test_domeincalls_zetten_huidig_domein_eenmalig_en_nooit_als_tool(rpc, fake):
    names = {t["name"] for t in rpc.req("tools/list")["result"]["tools"]}
    assert not any("set" in n and "domein" in n for n in names)
    fake.responses["DocumentFolders"] = "<Folders><Folder><ID>1</ID></Folder><Folder><ID>2</ID></Folder></Folders>"
    fake.responses["Currencies"] = "<Currencies><Currency><Code>EUR</Code></Currency><Currency><Code>USD</Code></Currency></Currencies>"
    assert data(rpc.call("yuki_archief_mappen", administratie=A))["aantal"] == 2
    rpc.call("yuki_archief_valuta", administratie=A)
    assert fake.methods().count("SetCurrentDomain") == 1
    r = rpc.call("yuki_archief_mappen")                         # accountantssleutel zonder domein
    assert r["isError"] is True and "domein" in r["content"][0]["text"]
    r2 = rpc.call("yuki_archief_mappen", domein_id="00000000-0000-0000-0000-0000000000ff", vernieuwen=True)
    assert r2["isError"] is False and fake.methods().count("SetCurrentDomain") == 2
    assert 'domainID' in [x for x in fake.requests if x[1] == "SetCurrentDomain"][0][2]


def test_set_current_domain_buiten_context_geweigerd(fake):
    import httpx
    t = PluginTransport("https://api.example.test/ws", http_client=httpx.Client(transport=httpx.MockTransport(fake.handler)))
    with pytest.raises(Exception):
        t.call("Accounting", "SetCurrentDomain", [("sessionID", "x"), ("domainID", "y")])
    assert fake.requests == []


def test_cli_alternatief(fake, capsys, monkeypatch):
    import importlib.util, pathlib, sys as _s
    from yuki_mcp.server import Server
    p = pathlib.Path(__file__).resolve().parents[1] / "server" / "run_cli.py"
    spec = importlib.util.spec_from_file_location("run_cli_t", p)
    m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
    srv = Server(__import__("yuki_mcp.clientfactory", fromlist=["x"]).ClientFactory(
        transport_factory=lambda: PluginTransport("https://api.example.test/ws", http_client=__import__("httpx").Client(transport=__import__("httpx").MockTransport(fake.handler)))))
    assert m.main(["list"], srv) == 0 and "yuki_status" in capsys.readouterr().out
    assert m.main(["yuki_status"], srv) == 0
    assert m.main(["yuki_status", "geen-json"], srv) == 2
    assert m.main(["schema", "bestaat-niet"], srv) == 2
