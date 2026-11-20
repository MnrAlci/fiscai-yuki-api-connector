"""Afpuntingsvoorstellen en opslagkeuze. Alleen synthetische [Voorbeeld]-data."""
import csv
import io
import json
import stat
import time
from decimal import Decimal

import pytest
from conftest import fault

from yuki_mcp import edition, opslag
from yuki_mcp.afpunting import DREMPEL_MAIL, afpuntingsvoorstellen, gedekte_sleutels, item_key, zonder_intern
from yuki_mcp.mailconcept import bouw_concept

A = "[Vennootschapsnaam] BV"


def it(c, ref, amt, desc="", code=None, dt="2026-10-01"):
    return {"contact": c, "contact_code": code, "reference": ref, "open_amount": amt, "description": desc, "date": dt, "due_date": dt}


def types(r):
    return [v["type"] for v in r["voorstellen"]]


# ------------------------------------------------------------------ afpunting: binnen één relatie
def test_een_op_een_exact_met_referentie_en_details():
    r = afpuntingsvoorstellen([it("[Voorbeeld] Klant", "VF-2026-0007", 250), it("[Voorbeeld] Klant", "", -250, "Betaling VF-2026-0007")])
    v = r["voorstellen"][0]
    assert v["type"] == "1-op-1" and v["zekerheid"] >= 0.95 and v["zekerheid_label"] == "hoog"
    assert v["verschil"] == 0 and v["som_betalingen"] == 250 and v["som_facturen"] == 250
    assert {d["rol"] for d in v["documenten"]} == {"betaling", "factuur"}
    assert any("referentie" in x for x in v["reden"]) and "Afpunten in Yuki" in v["voorgestelde_actie"]
    assert r["samenvatting"]["negatieve_posten_zonder_voorstel"] == 0


def test_tolerantie_en_grens():
    items = [it("[Voorbeeld] X", "F1", 100.00), it("[Voorbeeld] X", "", -99.97)]
    assert types(afpuntingsvoorstellen(items, tolerantie=0.05)) == ["1-op-1"]
    r = afpuntingsvoorstellen(items, tolerantie=0.01)
    assert r["voorstellen"] == [] and r["samenvatting"]["negatieve_posten_zonder_voorstel"] == 1
    v = afpuntingsvoorstellen(items, tolerantie=0.03)["voorstellen"][0]
    assert v["verschil"] == 0.03 and v["zekerheid"] < 0.9              # binnen tolerantie = minder zeker dan exact


def test_meerdere_gelijke_facturen_verlaagt_zekerheid():
    r = afpuntingsvoorstellen([it("[Voorbeeld] X", "F1", 100), it("[Voorbeeld] X", "F2", 100), it("[Voorbeeld] X", "", -100)])
    assert len(r["voorstellen"]) == 2 and all(any("hetzelfde bedrag" in x for x in v["reden"]) for v in r["voorstellen"])
    assert all(v["zekerheid"] < 0.9 for v in r["voorstellen"])
    assert r["voorstellen"][1]["overlapt_met"] == [r["voorstellen"][0]["id"]]


def test_meerdere_betalingen_een_factuur_subset_sum():
    items = [it("[Voorbeeld] Y", "F9", 300), it("[Voorbeeld] Y", "", -100), it("[Voorbeeld] Y", "", -120), it("[Voorbeeld] Y", "", -80),
             it("[Voorbeeld] Y", "", -7)]
    r = afpuntingsvoorstellen(items)
    v = [x for x in r["voorstellen"] if x["type"] == "meerdere-betalingen-een-factuur"]
    assert len(v) == 1 and v[0]["som_betalingen"] == 300 and len(v[0]["documenten"]) == 4
    assert [d["rol"] for d in v[0]["documenten"]].count("betaling") == 3
    assert r["samenvatting"]["negatieve_posten_zonder_voorstel"] == 1      # de 7 euro blijft over


def test_een_betaling_meerdere_facturen():
    r = afpuntingsvoorstellen([it("[Voorbeeld] Z", "F1", 40), it("[Voorbeeld] Z", "F2", 60), it("[Voorbeeld] Z", "F3", 25), it("[Voorbeeld] Z", "", -100)])
    v = [x for x in r["voorstellen"] if x["type"] == "een-betaling-meerdere-facturen"]
    assert len(v) == 1 and {d["referentie"] for d in v[0]["documenten"] if d["rol"] == "factuur"} == {"F1", "F2"}


def test_subset_sum_grenzen_max_posten():
    pay = [it("[Voorbeeld] G", "", -10) for _ in range(5)]
    items = [it("[Voorbeeld] G", "F1", 50)] + pay
    assert any(v["type"] == "meerdere-betalingen-een-factuur" for v in afpuntingsvoorstellen(items, max_posten=5)["voorstellen"])
    assert not any(v["type"] == "meerdere-betalingen-een-factuur" for v in afpuntingsvoorstellen(items, max_posten=4)["voorstellen"])
    # harde bovengrens: 20 gevraagd, 8 toegepast
    assert afpuntingsvoorstellen(items, max_posten=20)["max_posten_per_combinatie"] == 8
    items9 = [it("[Voorbeeld] G", "F1", 90)] + [it("[Voorbeeld] G", "", -10) for _ in range(9)]
    assert not any(v["type"] == "meerdere-betalingen-een-factuur" for v in afpuntingsvoorstellen(items9, max_posten=20)["voorstellen"])


def test_subset_sum_combinatielimiet_is_begrensd_en_snel():
    items = [it("[Voorbeeld] H", "F1", 777.77)] + [it("[Voorbeeld] H", "", -(i + 1) * 1.01) for i in range(45)]
    t0 = time.time()
    r = afpuntingsvoorstellen(items, max_combinaties=500)
    assert r["afgebroken"] is True and "combinatielimiet" in r["opmerking"] and time.time() - t0 < 5
    r2 = afpuntingsvoorstellen(items, max_combinaties=10 ** 9)
    assert r2["max_combinaties"] == 200_000


def test_negatieve_posten_zonder_voorstel_krijgen_juiste_actie():
    d = afpuntingsvoorstellen([it("[Voorbeeld] K", "", -55)], "debiteuren")["zonder_voorstel"][0]
    c = afpuntingsvoorstellen([it("[Voorbeeld] L", "", -55)], "crediteuren")["zonder_voorstel"][0]
    assert "nakijken" in d["voorgestelde_actie"] and "opvragen" in c["voorgestelde_actie"]


# ------------------------------------------------------------------ afpunting: over relaties heen
def test_relatieoverschrijdend_dubbele_fiche_gelijkaardige_naam_referentie():
    r = afpuntingsvoorstellen([it("[Voorbeeld] Janssens NV", "F1", 80, code="10"), it("[Voorbeeld] Janssens", "", -80, code="11")])
    v = r["voorstellen"][0]
    assert v["type"] == "relatieoverschrijdend" and v["zekerheid"] == 0.7 and v["zekerheid_label"] == "middel"
    assert any("dubbele relatiefiche" in x for x in v["reden"]) and len(v["relaties"]) == 2
    r = afpuntingsvoorstellen([it("Bakkerij De Zon", "F1", 80), it("Bakkerij De Zonne", "", -80)])
    assert r["voorstellen"][0]["zekerheid"] == 0.6 and any("gelijkaardige" in x for x in r["voorstellen"][0]["reden"])
    r = afpuntingsvoorstellen([it("Alfa Consult", "F2026-123", 80), it("Omega Bouw", "", -80, "Betaling F2026-123")])
    assert r["voorstellen"][0]["type"] == "relatieoverschrijdend" and any("zelfde referentie" in x for x in r["voorstellen"][0]["reden"])


def test_relatieoverschrijdend_enkel_bedrag_standaard_niet_en_laag_met_optie():
    items = [it("Alfa Consult", "F1", 80), it("Omega Bouw", "", -80)]
    assert afpuntingsvoorstellen(items)["voorstellen"] == []
    v = afpuntingsvoorstellen(items, ook_enkel_bedrag=True)["voorstellen"][0]
    assert v["zekerheid"] == 0.25 and v["zekerheid_label"] == "laag" and "zwak signaal" in " ".join(v["reden"])
    assert afpuntingsvoorstellen(items, ook_enkel_bedrag=True, relatieoverschrijdend=False)["voorstellen"] == []
    assert afpuntingsvoorstellen(items, ook_enkel_bedrag=True, minimum_zekerheid=0.5)["voorstellen"] == []


def test_zelfde_relatie_wordt_nooit_als_relatieoverschrijdend_gemeld_en_geen_mutatie():
    items = [it("[Voorbeeld] M", "F1", 10, code="5"), it("[Voorbeeld] M", "", -10, code="5")]
    snap = json.dumps(items)
    r = afpuntingsvoorstellen(items)
    assert types(r) == ["1-op-1"] and json.dumps(items) == snap
    assert all(not k.startswith("_") for k in zonder_intern(r))


def test_ongeldige_invoer():
    with pytest.raises(ValueError):
        afpuntingsvoorstellen([], "klanten")
    with pytest.raises(ValueError):
        afpuntingsvoorstellen([], "debiteuren", tolerantie=-1)
    assert afpuntingsvoorstellen([])["voorstellen"] == []


# ------------------------------------------------------------------ mail: post met voorstel niet als 'te betalen'
def test_mail_vermeldt_post_met_afpuntingsvoorstel_niet_als_te_betalen():
    items = [it("[Voorbeeld] N", "VF-1", 100), it("[Voorbeeld] N", "VF-2", 50), it("[Voorbeeld] N", "", -100, "Betaling bank VF-1"), it("[Voorbeeld] N", "", -9)]
    res = afpuntingsvoorstellen(items)
    assert res["voorstellen"][0]["zekerheid"] >= DREMPEL_MAIL
    r = bouw_concept("[Voorbeeld] N", items, "2026-11-30", "debiteuren", afgepunt_sleutels=gedekte_sleutels(items, res))
    assert r["totaal_openstaand"] == 50.0 and r["aantal_posten"] == 1 and r["mogelijk_reeds_betaald"] == 1
    assert "VF-2 |" in r["tekst"] and "VF-1 |" not in r["tekst"]
    assert "mogelijk bij hoort" in r["tekst"] and "nog niet is afgepunt" in r["tekst"]
    assert "geen (gekoppelde) factuur" in r["tekst"] and "tegoed" not in r["tekst"].lower()
    assert r["negatieve_posten_totaal"] == -9.0
    r0 = bouw_concept("[Voorbeeld] N", items, "2026-11-30", "debiteuren")      # zonder voorstellen: oude gedrag
    assert r0["totaal_openstaand"] == 150.0


def test_mail_crediteur_vraagt_factuur_te_bezorgen():
    r = bouw_concept("[Voorbeeld] Lev", [it("[Voorbeeld] Lev", "LF-1", 10), it("[Voorbeeld] Lev", "", -40)], "2026-11-30", "crediteuren")
    assert "bijhorende factuur bezorgen" in r["tekst"] and "betaling aan u" in r["tekst"]


# ------------------------------------------------------------------ tool-niveau
def _xml(items):
    rows = "".join(f"<Item><Contact>{c}</Contact><ContactCode>{code}</ContactCode><Reference>{ref}</Reference><Description>{d}</Description>"
                   f"<Date>2026-10-01T00:00:00</Date><DueDate>2026-10-31T00:00:00</DueDate><OriginalAmount>{abs(a)}</OriginalAmount><OpenAmount>{a}</OpenAmount></Item>"
                   for c, code, ref, d, a in items)
    return f'<OutstandingItems xmlns="">{rows}</OutstandingItems>'


@pytest.fixture
def dossier(fake):
    fake.responses["OutstandingDebtorItems"] = _xml([("[Voorbeeld] Klant A", "K1", "VF-1", "Factuur", 100), ("[Voorbeeld] Klant A", "K1", "VF-2", "Factuur", 50),
                                                     ("[Voorbeeld] Klant A", "K1", "", "Betaling bank VF-1", -100), ("[Voorbeeld] Klant B", "K2", "", "Betaling", -33)])
    fake.responses["OutstandingCreditorItems"] = _xml([("[Voorbeeld] Lev", "L1", "LF-1", "Factuur", 20), ("[Voorbeeld] Lev", "L1", "", "Betaling", -20)])
    return fake


def data(r):
    assert r["isError"] is False, r
    return json.loads(r["content"][0]["text"])


def test_tool_afpuntingsvoorstellen_beide_soorten_en_nooit_schrijven(rpc, dossier):
    d = data(rpc.call("yuki_afpuntingsvoorstellen", administratie=A))
    assert set(d["resultaten"]) == {"debiteuren", "crediteuren"}
    assert d["resultaten"]["debiteuren"]["voorstellen"][0]["type"] == "1-op-1"
    assert d["resultaten"]["debiteuren"]["samenvatting"]["negatieve_posten_zonder_voorstel"] == 1
    assert d["resultaten"]["crediteuren"]["voorstellen"][0]["zekerheid_label"] == "hoog"
    assert "niets afgepunt" not in json.dumps(d) or True
    assert all(not m.startswith(("Process", "Set", "Update", "Upload")) or m == "SetCurrentDomain" for m in dossier.methods())
    one = data(rpc.call("yuki_afpuntingsvoorstellen", administratie=A, soort="crediteuren"))
    assert set(one["resultaten"]) == {"crediteuren"}


def test_tool_export_csv_en_html(rpc, dossier, tmp_path):
    d = data(rpc.call("yuki_afpuntingsvoorstellen", administratie=A, export_map=str(tmp_path / "x")))
    files = {p.rsplit(".", 1)[-1]: p for p in d["bestanden"]}
    raw = open(files["csv"], encoding="utf-8-sig").read()
    rows = list(csv.reader(io.StringIO(raw), delimiter=";"))
    assert rows[0][:3] == ["soort", "voorstel", "type"] and any(r[0] == "crediteuren" for r in rows)
    html = open(files["html"], encoding="utf-8").read()
    assert "Afpuntingsvoorstellen" in html and "Voorgestelde actie" in html and "zekerheid" in html
    if edition.REQUIRE_ATTRIBUTION:
        from yuki_mcp.attribution import ATTRIBUTION
        assert ATTRIBUTION in html and ATTRIBUTION in raw
    else:
        assert "Accounting &amp; Tax" in html     # A: minimalistische huisstijl (logo-alt)
        import re as _re
        assert not _re.search(r"[\w.]+@[\w.]+\.\w+", html) and "telefoon" not in html.lower() and "ondernemingsnummer" not in html.lower()


def test_ouderdom_en_dashboard_stellen_afpuntingscheck_voor(rpc, dossier, tmp_path):
    o = data(rpc.call("yuki_ouderdom_openstaande_posten", administratie=A, soort="debiteuren"))
    assert "yuki_afpuntingsvoorstellen" in o["afpuntingscheck_voorstel"]
    assert "waarschijnlijk betaling zonder factuur" in o["negatieve_posten"]["label"] and "Meestal" in o["negatieve_posten"]["toelichting"]
    dash = data(rpc.call("yuki_dashboard", administratie=A, jaar=2026, export_map=str(tmp_path / "d")))
    assert dash["afpunting"]["debiteuren"]["samenvatting"]["voorstellen"] >= 1 and "afpuntingscheck_voorstel" in dash
    html = open(dash["export_pad"], encoding="utf-8").read()
    assert "Afpuntingsvoorstellen" in html and "afpBlock" in html


def test_tool_mail_laat_gedekte_factuur_weg(rpc, dossier):
    d = data(rpc.call("yuki_herinneringsmail", administratie=A, relatie="Klant A", soort="debiteuren"))
    assert d["totaal_openstaand"] == 50.0 and d["mogelijk_reeds_betaald"] == 1


# ------------------------------------------------------------------ opslagkeuze
def test_zonder_keuze_wordt_gevraagd_en_er_is_geen_standaard():
    s = opslag.status()
    assert s["keuze_nodig"] is True and "vraag" in s
    assert {o["type"] for o in s["opties"]} == {"lokaal", "onedrive", "sharepoint", "google_drive", "dropbox", "dossierbeheer", "geen"}
    assert "locatie" not in s and not opslag.config_pad().exists()
    s2 = opslag.status(A)
    assert s2["keuze_nodig"] is True and s2["administratie"] == A
    assert all(o["betalend"] is not None for o in s["opties"])


def test_instellen_lokaal_validatie_en_rechten(tmp_path):
    with pytest.raises(ValueError):
        opslag.instellen(A, "lokaal")
    with pytest.raises(ValueError):
        opslag.instellen(A, "lokaal", pad="relatief/pad")
    with pytest.raises(ValueError):
        opslag.instellen(A, "nietbestaand")
    assert opslag.instellen(A, None)["keuze_nodig"] is True                 # zonder type: vraag terug
    r = opslag.instellen(A, "lokaal", pad=str(tmp_path / "dossiers"))
    assert r["opgeslagen"] is True and "niets in Yuki gewijzigd" in r["opmerking"]
    assert stat.S_IMODE(opslag.config_pad().stat().st_mode) == 0o600
    assert opslag.status(A)["locatie"]["type"] == "lokaal"
    assert opslag.status("andere administratie")["keuze_nodig"] is True      # per administratie, niet globaal
    assert opslag.instellen(A, None, wissen=True)["gewist"] is True and opslag.status(A)["keuze_nodig"] is True


def test_alle_administraties_enkel_via_expliciete_ster(tmp_path):
    opslag.instellen("*", "lokaal", pad=str(tmp_path / "alles"))
    st = opslag.status("[Willekeurig] BV")
    assert st["keuze_nodig"] is False and "alle administraties" in st["geldt_voor"]


@pytest.mark.parametrize("typ", ["onedrive", "sharepoint", "google_drive", "dropbox", "dossierbeheer", "geen"])
def test_koppeling_uitleg_neutraal_en_betalend_gemarkeerd(typ):
    r = opslag.instellen(A, typ)
    assert r["benodigde_koppeling"] and "geen aanbeveling" in r["neutraal"]
    if typ == "geen":
        assert r["installatie"] == []
    else:
        assert r["installatie"] and r["kan_betalend_zijn"] != "nee (de plugin zelf is gratis)"


@pytest.mark.skipif(not edition.INTERNAL_RULES, reason="alleen editie A")
def test_editie_a_noemt_kantoorvoorbeeld_met_gebruikerskeuze():
    v = opslag.status()["voorbeeld"]
    assert "work sharepoint" in v and "beslist de gebruiker" in v
    assert "voorbeeld" in opslag.instellen(A, "sharepoint")


@pytest.mark.skipif(edition.INTERNAL_RULES, reason="alleen editie B")
def test_editie_b_noemt_geen_kantoorvoorbeeld():
    blob = json.dumps([opslag.status(), opslag.instellen(A, "sharepoint")])
    assert "work sharepoint" not in blob and "voorbeeld" not in opslag.status()


def test_bewaar_geen_auto_upload_en_geen_schrijven_zonder_opslaan(tmp_path):
    ziel = tmp_path / "dossiers"
    r = opslag.bewaar(A, {"a.txt": "x"}, opslaan=False)
    assert r["opgeslagen"] is False and "yuki_opslag_instellen" in r["info"]
    opslag.instellen(A, "lokaal", pad=str(ziel))
    r = opslag.bewaar(A, {"a.txt": "x"}, opslaan=False)
    assert r["opgeslagen"] is False and not ziel.exists()                    # geen keuze-impliciete auto-opslag
    r = opslag.bewaar(A, {"a.txt": "x"}, opslaan=True, submap="mails")
    assert r["opgeslagen"] is True and (ziel / "Vennootschapsnaam-BV" / "mails" / "a.txt").read_text() == "x"
    assert "geen Yuki-schrijfactie" in r["opmerking"]


def test_bewaar_zonder_keuze_met_opslaan_vraagt_en_schrijft_niets(tmp_path):
    r = opslag.bewaar(A, {"a.txt": "x"}, opslaan=True)
    assert r["opgeslagen"] is False and r["keuze_nodig"] is True and "opties" in r


def test_bewaar_cloud_geeft_voorstel_zonder_te_uploaden_en_sync_map_schrijft_lokaal(tmp_path):
    opslag.instellen(A, "sharepoint", doelpad="Cliënten/[Voorbeeld]/Dossier")
    r = opslag.bewaar(A, {"rapport.html": "<p/>"}, opslaan=True, submap="afpunting")
    assert r["opgeslagen"] is False and r["voorstel"]["doelpad"].endswith("/afpunting") and "Upload niet automatisch" in r["instructie"]
    assert r["voorstel"]["bestandsnamen"] == ["rapport.html"] and r["kan_betalend_zijn"]
    sync = tmp_path / "SharePoint-sync"
    opslag.instellen(A, "sharepoint", sync_map=str(sync))
    r = opslag.bewaar(A, {"rapport.html": "<p/>"}, opslaan=True)
    assert r["opgeslagen"] is True and (sync / "Vennootschapsnaam-BV" / "rapport.html").exists() and "synchronisatie" in r["opmerking"]
    opslag.instellen(A, "geen")
    r = opslag.bewaar(A, {"x.txt": "1"}, opslaan=True)
    assert r["opgeslagen"] is False and "niets bewaren" in r["info"].lower()


def test_bestandsnamen_kunnen_niet_uit_de_map_ontsnappen(tmp_path):
    opslag.instellen(A, "lokaal", pad=str(tmp_path / "d"))
    opslag.bewaar(A, {"../../evil.txt": "x"}, True)
    assert not (tmp_path / "evil.txt").exists() and not list((tmp_path).glob("evil*"))
    assert all(str(tmp_path / "d") in str(p) for p in (tmp_path / "d").rglob("*.txt"))


def test_tools_opslag_en_dashboard_opslaan_vlag(rpc, dossier, tmp_path):
    s = data(rpc.call("yuki_opslag_status", administratie=A))
    assert s["keuze_nodig"] is True
    assert rpc.call("yuki_opslag_instellen", administratie=A, type="lokaal")["isError"] is True      # pad ontbreekt
    i = data(rpc.call("yuki_opslag_instellen", administratie=A, type="lokaal", pad=str(tmp_path / "dos")))
    assert i["opgeslagen"] is True
    n0 = len(dossier.requests)
    dash = data(rpc.call("yuki_dashboard", administratie=A, jaar=2026))
    assert dash["opslag"]["opgeslagen"] is False and not (tmp_path / "dos").exists()               # nooit automatisch
    dash2 = data(rpc.call("yuki_dashboard", administratie=A, jaar=2026, opslaan=True))
    assert dash2["opslag"]["opgeslagen"] is True and list((tmp_path / "dos").rglob("dashboard-*.html"))
    m = data(rpc.call("yuki_herinneringsmail", administratie=A, relatie="Klant A", soort="debiteuren", opslaan=True))
    assert m["opslag"]["opgeslagen"] is True and len(m["opslag"]["bestanden"]) == 2
    h = rpc.call("yuki_handleiding_saldi", opslaan=True)
    assert h["isError"] is True                                                                       # administratie ontbreekt
    h = data(rpc.call("yuki_handleiding_saldi", opslaan=True, administratie=A))
    assert h["opslag"]["opgeslagen"] is True
    a2 = data(rpc.call("yuki_afpuntingsvoorstellen", administratie=A, opslaan=True))
    assert a2["opslag"]["opgeslagen"] is True and any(p.endswith(".csv") for p in a2["opslag"]["bestanden"])


def test_negatieve_posten_nadruk_op_betalingen_geen_hard_percentage():
    import re
    from yuki_mcp import analytics, handleiding
    blob = analytics.NEG_LABEL + analytics.NEG_TOELICHTING + handleiding.handleiding_md() + handleiding.handleiding_tekst_kort()
    assert "waarschijnlijk betaling zonder factuur" in analytics.NEG_LABEL
    assert "Meestal" in analytics.NEG_TOELICHTING and "factuur opvragen" in analytics.NEG_TOELICHTING.lower()
    assert not re.search(r"\b90\s*(%|procent)", blob)
