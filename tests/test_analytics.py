from datetime import date
from decimal import Decimal

import pytest
from yuki_mcp import analytics as an


class It:
    def __init__(s, contact, open_amount, due=None, d=None):
        s.contact, s.open_amount, s.due_date, s.date = contact, Decimal(str(open_amount)), due, d


PEIL = date(2026, 11, 30)
ITEMS = [It("A", 100, date(2026, 12, 15)), It("A", 200, date(2026, 11, 20)), It("B", 300, date(2026, 10, 15)),
         It("B", 400, date(2026, 9, 15)), It("C", 500, date(2026, 6, 1)), It("D", -150, date(2026, 10, 1)), It("E", 50, None)]


def test_ouderdom_buckets_exact():
    r = an.ouderdomsanalyse(ITEMS, PEIL)
    b = r["buckets"]
    assert b["niet_vervallen"] == {"bedrag": 100.0, "aantal": 1}
    assert b["0-30"]["bedrag"] == 200.0          # 10 dagen
    assert b["31-60"]["bedrag"] == 300.0         # 46 dagen
    assert b["61-90"]["bedrag"] == 400.0         # 76 dagen
    assert b[">90"]["bedrag"] == 500.0
    assert b["zonder_datum"]["bedrag"] == 50.0
    assert r["negatieve_posten"]["bedrag"] == -150.0 and r["negatieve_posten"]["aantal"] == 1 and "na te gaan" in r["negatieve_posten"]["label"] and "tegoed" not in r["negatieve_posten"]["label"].lower()
    assert r["totaal_positief"] == 1550.0 and r["netto"] == 1400.0 and r["vervallen_totaal"] == 1400.0


def test_ouderdom_grenzen():
    assert an.bucket_for(0) == "niet_vervallen" and an.bucket_for(1) == "0-30" and an.bucket_for(30) == "0-30"
    assert an.bucket_for(31) == "31-60" and an.bucket_for(60) == "31-60" and an.bucket_for(61) == "61-90"
    assert an.bucket_for(90) == "61-90" and an.bucket_for(91) == ">90"


def test_ouderdom_ongeldige_basis():
    with pytest.raises(ValueError):
        an.ouderdomsanalyse(ITEMS, PEIL, "x")


def test_dso_formule():
    r = an.dagen_ratio(Decimal(30000), Decimal(365000), 365)
    assert r["waarde_dagen"] == 30.0
    r2 = an.dagen_ratio(Decimal(30000), Decimal(100000), 100, btw_percentage=21)
    assert r2["waarde_dagen"] == 24.8 and r2["basis"] == 121000.0
    assert an.dagen_ratio(1, 0, 10)["waarde_dagen"] is None


def test_top_relaties():
    t = an.top_relaties(ITEMS, 2)
    assert [x["relatie"] for x in t] == ["B", "C"] and t[0]["openstaand"] == 700.0 and t[0]["posten"] == 2
    assert t[0]["oudste_vervaldatum"] == "2026-09-15"


L_END = [{"code": "700000", "balance": -1000}, {"code": "600000", "balance": 300}, {"code": "610000", "balance": 200},
         {"code": "620000", "balance": 100}, {"code": "550000", "balance": 5000}, {"code": "690000", "balance": 50}]
L_PREV = [{"code": "700000", "balance": -400}, {"code": "600000", "balance": 100}, {"code": "610000", "balance": 100}]


def test_pl_periode_jaar_en_delta():
    p = an.pl_periode(L_END)
    assert p["omzet"] == 1000 and p["kosten"] == 600 and p["resultaat"] == 400 and p["inkopen_60"] == 300
    d = an.pl_periode(L_END, L_PREV)
    assert d["omzet"] == 600 and d["kosten"] == 400 and d["resultaat"] == 200      # 69 telt niet mee


def test_marge_en_kostenstructuur():
    m = an.marge_kostenstructuur(an.pl_periode(L_END))
    assert m["brutomarge"] == 700.0 and m["brutomarge_pct"] == 70.0 and m["nettomarge_pct"] == 40.0
    assert {k["klasse"]: k["bedrag"] for k in m["kostenstructuur"]} == {"60": 300.0, "61": 200.0, "62": 100.0}


@pytest.mark.parametrize("periode,verwacht", [("jaar", (date(2026, 1, 1), date(2026, 12, 31))),
                                              ("kwartaal:1", (date(2026, 1, 1), date(2026, 3, 31))),
                                              ("kwartaal:4", (date(2026, 10, 1), date(2026, 12, 31))),
                                              ("maand:2", (date(2026, 2, 1), date(2026, 2, 28))),
                                              ("maand:12", (date(2026, 12, 1), date(2026, 12, 31)))])
def test_periode_bereik(periode, verwacht):
    assert an.periode_bereik(2026, periode) == verwacht


def test_vorige_periode():
    assert an.vorige_periode(2026, "maand:1") == (2025, "maand:12")
    assert an.vorige_periode(2026, "kwartaal:3") == (2026, "kwartaal:2")
    assert an.vorige_periode(2026, "jaar") == (2025, "jaar")
    with pytest.raises(ValueError):
        an.periode_bereik(2026, "week:1")


def test_vergelijk():
    v = an.vergelijk(an.pl_periode(L_END), an.pl_periode(L_PREV))
    assert v["omzet"]["verschil"] == 600.0 and v["omzet"]["verschil_pct"] == pytest.approx(150.0, abs=0.1)


def test_btw_indicatie():
    r = an.btw_saldo_indicatie([{"code": "451000", "balance": -800}, {"code": "411000", "balance": 300}, {"code": "400000", "balance": 9}])
    assert r["btw_te_betalen_451"] == 800.0 and r["btw_te_vorderen_411"] == 300.0 and r["netto_te_betalen"] == 500.0


class Tx:
    def __init__(s, id, amt, desc="x", d="2026-01-01"):
        s.id, s.amount, s.description, s.date = id, Decimal(str(amt)), desc, d


def test_uitschieters_en_dubbels():
    txs = [Tx(i, 100 + (i % 3), "x", f"2026-01-{i + 1:02d}") for i in range(12)] + [Tx("grote", 9000), Tx("dup1", 101, "zelfde", "2026-02-02"), Tx("dup2", 101, "zelfde", "2026-02-02")]
    r = an.uitschieters(txs)
    assert [u["id"] for u in r["uitschieters"]] == ["grote"]
    assert len(r["mogelijk_dubbel"]) == 1 and r["mogelijk_dubbel"][0]["aantal"] == 2


def test_uitschieters_te_weinig_data():
    assert an.uitschieters([Tx(1, 1)])["uitschieters"] == []


def test_analyses_via_tools(rpc):
    import json
    A = "[Vennootschapsnaam] BV"
    for name, args in [("yuki_ouderdom_openstaande_posten", dict(soort="debiteuren")), ("yuki_top_relaties", dict(soort="debiteuren")),
                       ("yuki_liquiditeit", dict(datum="2026-09-30")), ("yuki_marge_kostenstructuur", dict(jaar=2026)),
                       ("yuki_periodevergelijking", dict(jaar=2026, periode="kwartaal:3")),
                       ("yuki_uitschieters", dict(rekening="550000", van="2026-10-01", to="x", tot="2026-10-31")),
                       ("yuki_dso_dpo", dict(jaar=2026, tot="2026-09-30"))]:
        args.pop("to", None)
        r = rpc.call(name, administratie=A, **args)
        assert r["isError"] is False, (name, r)
        out = json.loads(r["content"][0]["text"])
        assert out["bronnen"], name


def test_negatief_type_enkel_uit_yuki_gegevens():
    from yuki_mcp.analytics import negatief_type, ouderdomsanalyse
    assert negatief_type({"description": "Creditnota 2026-11", "reference": "CN1"}) == "creditnota"
    assert negatief_type({"description": "Betaling bank 12/11", "reference": ""}) == "betaling"
    assert negatief_type({"description": "Voorschot project", "reference": ""}) == "voorschot"
    assert negatief_type({"description": "", "reference": "X-77"}) == "onbekend type"
    assert negatief_type({"description": "creditnota betaling", "reference": ""}) == "onbekend type"   # dubbelzinnig: niet gokken
    r = ouderdomsanalyse([{"open_amount": -10, "description": "Betaling bank"}, {"open_amount": -5, "description": "x"}], "2026-11-30")
    assert r["negatieve_posten"]["types"] == {"betaling": 1, "onbekend type": 1}


def test_dashboard_kpis_tool(rpc):
    import json
    A = "[Vennootschapsnaam] BV"
    r = rpc.call("yuki_dashboard_kpis", administratie=A, jaar=2026, peildatum="2026-09-30", vergelijk_vorige_periode=True)
    assert r["isError"] is False, r
    out = json.loads(r["content"][0]["text"])
    for k in ("periode", "omzet", "kosten", "resultaat", "liquide_middelen", "open_debiteuren", "open_crediteuren", "marge", "liquiditeit", "dso", "dpo", "btw_indicatie", "vergelijking_vorige_periode"):
        assert k in out, k
    assert out["bronnen"] and any("geen fiscaal advies" in a.lower() for a in out["aannames"])


def test_portfolio_kpis_tool_en_limiet(rpc):
    import json
    A = "[Vennootschapsnaam] BV"
    r = rpc.call("yuki_portfolio_kpis", administraties=[A, "[Bestaat niet] BV"], jaar=2026)
    assert r["isError"] is False, r
    out = json.loads(r["content"][0]["text"])
    assert out["aantal_administraties"] == 2 and out["aantal_fouten"] == 1
    ok = [x for x in out["administraties"] if "fout" not in x]
    assert len(ok) == 1 and ok[0]["omzet"] == out["totaal"]["omzet"]
    te_veel = rpc.call("yuki_portfolio_kpis", administraties=[A] * 6, jaar=2026, max_administraties=5)
    assert te_veel["isError"] is True



def test_export_dataset_formaten_en_schema(rpc, tmp_path):
    import csv, json, zipfile
    A = "[Vennootschapsnaam] BV"
    for ds, extra in (("kpis", dict(jaar=2026)), ("saldi", dict(jaar=2026, peildatum="2026-09-30")), ("openstaande_posten", dict(soort="debiteuren"))):
        r = rpc.call("yuki_export_dataset", dataset=ds, administratie=A, formaten=["csv", "json", "xlsx"], export_map=str(tmp_path), **extra)
        assert r["isError"] is False, r
        out = json.loads(r["content"][0]["text"])
        assert out["aantal_rijen"] >= 1 and len(out["bestanden"]) == 3
        from yuki_mcp import export as exp
        with open(tmp_path / f"yuki-{ds}.csv", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            assert rd.fieldnames == exp.cols(ds)
            assert len(list(rd)) == out["aantal_rijen"]
        js = json.loads((tmp_path / f"yuki-{ds}.json").read_text(encoding="utf-8"))
        assert js["dataset"] == ds and len(js["rijen"]) == out["aantal_rijen"] and [c["naam"] for c in js["schema"]] == exp.cols(ds)
        with zipfile.ZipFile(tmp_path / f"yuki-{ds}.xlsx") as z:
            assert "xl/worksheets/sheet1.xml" in z.namelist() and b"<sheetData>" in z.read("xl/worksheets/sheet1.xml")


def test_export_dataset_zonder_map_schrijft_niets_en_valideert(rpc, tmp_path):
    import json
    A = "[Vennootschapsnaam] BV"
    r = rpc.call("yuki_export_dataset", dataset="saldi", administratie=A, jaar=2026)
    out = json.loads(r["content"][0]["text"])
    assert "bestanden" not in out and out["schema"]
    assert rpc.call("yuki_export_dataset", dataset="onbekend", administratie=A)["isError"] is True
    assert rpc.call("yuki_export_dataset", dataset="saldi", administratie=A, formaten=["pdf"])["isError"] is True


def test_export_parquet_optioneel(rpc, tmp_path):
    import json
    A = "[Vennootschapsnaam] BV"
    r = rpc.call("yuki_export_dataset", dataset="saldi", administratie=A, jaar=2026, formaten=["parquet"], export_map=str(tmp_path))
    try:
        import pyarrow  # noqa: F401
        assert r["isError"] is False and (tmp_path / "yuki-saldi.parquet").exists()
    except ImportError:
        assert r["isError"] is True and "pyarrow" in r["content"][0]["text"]
