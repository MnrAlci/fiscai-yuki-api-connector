"""Dossieroverdracht per boekjaar: schatting, bevestiging, checkpoint, MANIFEST, CONTROL. Offline, [Voorbeeld]-gegevens."""
import csv
import hashlib
import json
import zipfile
from decimal import Decimal
from pathlib import Path

import pytest

from yuki_mcp import cli, transfer
from yuki_mcp.tools import Tools


class YukiDailyLimitReached(Exception):
    pass


def line(code, b):
    b = Decimal(b)
    return {"code": code, "name": f"[Voorbeeld] {code}", "debit": str(max(b, 0)), "credit": str(max(-b, 0)), "balance": str(b)}


TB = {
    ("2025-12-31", "commercieel"): {"400000": 100, "550000": 1000, "100000": -500, "700000": -600},
    ("2024-12-31", "commercieel"): {"400000": 80, "550000": 420, "100000": -500, "700000": 0},
    ("2024-12-31", "jaarafsluiting"): {"400000": 80, "550000": 420, "100000": -500},
    ("2025-12-31", "jaarafsluiting"): {"400000": 100, "550000": 1000, "100000": -500},
    ("2023-12-31", "commercieel"): {},
}
ENTRIES = {("2025", "400000"): ["20.00"], ("2025", "550000"): ["580.00"], ("2025", "700000"): ["-600.00"],
           ("2024", "400000"): ["80.00"], ("2024", "550000"): ["420.00"], ("2024", "100000"): ["-500.00"]}


class Fake:
    def __init__(self, limit_after=None, tamper=False):
        self.calls, self.limit_after, self.tamper = [], limit_after, tamper

    def __call__(self, name, a):
        if self.limit_after is not None and len(self.calls) >= self.limit_after:
            raise YukiDailyLimitReached("daglimiet")
        self.calls.append((name, (a["rekening"] + "@" + a["van"][:4]) if a.get("rekening") else (a.get("datum") or a.get("soort") or "")))
        if name == "yuki_rekeningschema":
            return [{"code": c, "name": f"[Voorbeeld] {c}"} for c in ("100000", "400000", "550000", "700000", "999999")]
        if name == "yuki_status":
            return {"domains": [{"remaining": 900}], "limit": 900}
        if name == "yuki_proefbalans":
            return [line(c, b) for c, b in TB[(a["datum"], a["soort"])].items()]
        if name == "yuki_grootboekmutaties":
            vals = ENTRIES.get((a["van"][:4], a["rekening"]), [])
            if self.tamper and a["rekening"] == "550000" and a["van"].startswith("2025"):
                vals = ["500.00"]
            return [{"id": f"[Voorbeeld]-{i}", "date": a["van"], "description": "[Voorbeeld]", "amount": v, "gl_account_code": a["rekening"]} for i, v in enumerate(vals)]
        if name == "yuki_openstaande_posten":
            return [{"contact": "[Voorbeeld] Klant", "open_amount": "100.00"}] if a["soort"] == "debiteuren" and a["peildatum"].startswith("2025") else []
        if name == "yuki_klanten_leveranciers":
            return {"gegevens": [{"naam": "[Voorbeeld] Klant", "btw": "BE0000000000"}]}
        if name == "yuki_archief_documenten":
            return {"gegevens": [{"documentID": "00000000-0000-0000-0000-000000000000", "naam": "[Voorbeeld].pdf"}]}
        return []


def run(tmp, call=None, **kw):
    args = dict(administratie="[Voorbeeld] BV", years=[2024, 2025], out=tmp, confirmed=True)
    args.update(kw)
    return transfer.run_export(call or Fake(), **args)


def test_schatting_zonder_export(tmp_path):
    f = Fake()
    r = run(tmp_path / "o", f, estimate_only=True, confirmed=False)
    assert r["status"] == "schatting" and r["estimate"]["max_calls"] > 0 and len(f.calls) <= 2
    assert not (tmp_path / "o").exists() or not list((tmp_path / "o").iterdir())


def test_bevestiging_boven_drempel_en_boven_resterend(tmp_path):
    r = run(tmp_path / "o", Fake(), confirmed=False, threshold=5)
    assert r["status"] == "bevestiging_nodig" and r["needs_confirmation"] and not (tmp_path / "o" / "2025").exists()
    low = Fake()
    low_status = lambda n, a: ({"domains": [{"remaining": 3}]} if n == "yuki_status" else low(n, a))  # noqa: E731
    r2 = run(tmp_path / "o2", low_status, confirmed=False, threshold=10000)
    assert r2["estimate"]["exceeds_remaining"] and r2["status"] == "bevestiging_nodig"


def test_volledige_export_per_jaar_met_manifest_control_en_readme(tmp_path):
    out = tmp_path / "o"
    r = run(out, zip_years=True)
    assert r["status"] == "klaar" and not r["failed_steps"]
    for y in ("2024", "2025"):
        for n in ("rekeningschema", "proefbalans-slot", "proefbalans-begin", "proefbalans-jaarafsluiting", "startbalans-api", "grootboekmutaties", "openstaande-debiteuren-einde",
                  "openstaande-crediteuren-einde", "contacten", "btw-aangiften", "btw-codes", "klasse-2-saldi-indicatie"):
            assert (out / y / f"{n}.csv").is_file() and (out / y / f"{n}.json").is_file(), (y, n)
        assert not (out / y / "archief-documenten-metadata.csv").exists()            # alleen met --include-documents
        assert not (out / y / "_delen").exists()
        m = json.loads((out / y / "MANIFEST.json").read_text())
        assert m["fiscal_year"] == int(y) and m["read_only"] is True
        for f in m["files"]:
            assert hashlib.sha256((out / y / f["file"]).read_bytes()).hexdigest() == f["sha256"]
        gm = next(f for f in m["files"] if f["file"] == "grootboekmutaties.csv")
        assert gm["rows"] == len(list(csv.DictReader(open(out / y / "grootboekmutaties.csv", encoding="utf-8"))))
        assert zipfile.ZipFile(out / f"{y}.zip").testzip() is None
    ctrl = (out / "2025" / "CONTROL.md").read_text(encoding="utf-8")
    assert "AFWIJKING" not in ctrl and "Beginbalans 2025 = slotbalans 2024" in ctrl and "OK" in ctrl
    assert "niet gecontroleerd" in (out / "2024" / "CONTROL.md").read_text(encoding="utf-8")        # 2023 niet geëxporteerd
    rd = (out / "README.md").read_text(encoding="utf-8")
    assert "Powered by FISCALCI Accounting & Tax (Askin Alci)" in rd and "Belgische" in rd and "verifieer actuele regel" in rd and "GDPR" in rd and "MAR/PCMN" in rd
    assert "geen activaregister" in rd.lower() or "activaregister" in rd


def test_controle_ziet_afwijking(tmp_path):
    out = tmp_path / "o"
    run(out, Fake(tamper=True))
    assert "AFWIJKING" in (out / "2025" / "CONTROL.md").read_text(encoding="utf-8")
    m = json.loads((out / "2025" / "MANIFEST.json").read_text())
    assert m["control_summary"]["afwijkingen"] >= 1


def test_documentmetadata_alleen_met_optie(tmp_path):
    out = tmp_path / "o"
    run(out, years=[2025], include_documents=True)
    assert (out / "2025" / "archief-documenten-metadata.csv").is_file()
    assert json.loads((out / "2025" / "MANIFEST.json").read_text())["documents_metadata_included"] is True


def test_hervatten_na_daglimiet(tmp_path):
    out = tmp_path / "o"
    f1 = Fake(limit_after=14)
    r1 = run(out, f1)
    assert r1["status"] == "onderbroken" and "hervatten" in r1["interrupted"] and (out / transfer.CHECKPOINT).is_file()
    assert not (out / "README.md").exists()                      # pas na een volledige run
    f2 = Fake()
    r2 = run(out, f2)
    assert r2["status"] == "klaar"
    done_first = {c for c in f1.calls if c[0] == "yuki_grootboekmutaties"}
    again = [c for c in f2.calls if c in done_first]
    assert not again, "reeds opgehaalde rekeningen mogen niet opnieuw worden opgevraagd"
    full = Fake()
    run(tmp_path / "vers", full)
    assert len(f1.calls) + len(f2.calls) - 2 <= len(full.calls) + 3        # hoogstens de schatting-calls extra
    assert (out / "2025" / "MANIFEST.json").is_file()


def test_checkpoint_van_andere_instellingen_wordt_geweigerd(tmp_path):
    out = tmp_path / "o"
    run(out, years=[2025])
    with pytest.raises(transfer.TransferError, match="checkpoint"):
        run(out, years=[2024, 2025])


def test_ongeldige_invoer(tmp_path):
    for kw in ({"years": []}, {"years": [1800]}, {"start_month": 13}, {"years": list(range(2000, 2020))}):
        with pytest.raises(transfer.TransferError):
            run(tmp_path / "x", **kw)


def test_gebroken_boekjaar_en_xlsx(tmp_path):
    assert transfer.year_bounds(2025) == (__import__("datetime").date(2025, 1, 1), __import__("datetime").date(2025, 12, 31))
    assert transfer.year_bounds(2025, 7)[1].isoformat() == "2026-06-30"
    p = tmp_path / "t.xlsx"
    transfer.write_xlsx(p, [{"a": "1,5", "b": "é & <x>"}])
    z = zipfile.ZipFile(p)
    assert z.testzip() is None and "xl/worksheets/sheet1.xml" in z.namelist() and "&amp;" in z.read("xl/worksheets/sheet1.xml").decode()


def test_stap_fout_stopt_de_rest_niet_en_blijft_hervatbaar(tmp_path):
    class Boom(Fake):
        def __call__(self, name, a):
            if name == "yuki_btw_aangiftes":
                raise RuntimeError("btw niet beschikbaar")
            return super().__call__(name, a)
    r = run(tmp_path / "o", Boom(), years=[2025])
    assert r["status"] == "klaar" and any(k.endswith(":vat") for k in r["failed_steps"])
    assert (tmp_path / "o" / "2025" / "grootboekmutaties.csv").is_file()
    assert json.loads((tmp_path / "o" / "2025" / "MANIFEST.json").read_text())["failed_steps"]
    f = Fake()
    run(tmp_path / "o", f, years=[2025])                         # hervat: alleen de mislukte stap opnieuw
    assert [c[0] for c in f.calls if c[0] not in ("yuki_rekeningschema", "yuki_status")] == ["yuki_btw_aangiftes"]


# ---------------------------------------------------------------- tool en CLI
def test_tool_is_alleen_lezen_en_gevalideerd():
    from yuki_mcp.clientfactory import ClientFactory
    t = Tools(ClientFactory())
    d = t.defs["yuki_dossier_transfer_export"]
    assert d["annotations"]["readOnlyHint"] is True and set(d["inputSchema"]["required"]) == {"administratie", "export_map"}
    with pytest.raises(Exception):
        t.call("yuki_dossier_transfer_export", {"administratie": "x"})              # export_map ontbreekt
    with pytest.raises(Exception):
        t.call("yuki_dossier_transfer_export", {"administratie": "x", "export_map": "/tmp/x", "raar": 1})
    for n in transfer.TOOLS_USED:
        assert n in t.defs and t.defs[n]["annotations"]["readOnlyHint"] is True, n


@pytest.fixture
def fake_tools(monkeypatch):
    from yuki_mcp.clientfactory import ClientFactory
    f = Fake()
    t = Tools(ClientFactory())
    for n in transfer.TOOLS_USED:
        t.handlers[n] = (lambda a, n=n: f(n, a))
    monkeypatch.setattr(cli, "_tools", lambda: t)
    return f


def test_cli_dry_run_en_gebruik(fake_tools, tmp_path, capsys):
    assert cli.main(["transfer", "export", "--administration", "[Voorbeeld] BV", "--fiscal-year", "2025", "--out", str(tmp_path / "o"), "--dry-run", "--json"]) == 0
    assert json.loads(capsys.readouterr().out)["network"] is False and not fake_tools.calls
    assert cli.main(["transfer", "export", "--administration", "x", "--out", str(tmp_path)]) == cli.EXIT_USAGE      # geen jaren
    assert cli.main(["transfer"]) == cli.EXIT_USAGE


def test_cli_vraagt_bevestiging_boven_drempel(fake_tools, tmp_path, capsys):
    a = ["transfer", "export", "--administration", "[Voorbeeld] BV", "--fiscal-year", "2025", "--out", str(tmp_path / "o"), "--threshold", "5"]
    assert cli.main(a) == cli.EXIT_REFUSED                                              # niet-interactief, geen --yes
    assert not (tmp_path / "o" / "2025").exists()
    assert "--yes" in capsys.readouterr().err
    assert cli.main(a + ["--yes", "--zip"]) == 0
    assert (tmp_path / "o" / "2025" / "CONTROL.md").is_file() and (tmp_path / "o" / "2025.zip").is_file()
    assert cli.main(["transfer", "export", "--administration", "x", "--fiscal-year", "2025", "--out", str(tmp_path / "e"), "--estimate-only"]) == 0
    assert not (tmp_path / "e" / "2025").exists()


def test_on_export_hook_bij_transfer():
    from yuki_mcp.hooks import Hooks, guarded_call
    seen = []

    class H(Hooks):
        def __init__(self):
            pass

        def fire(self, ev, payload):
            seen.append((ev, payload))
    guarded_call(H(), lambda n, a: {"status": "klaar"}, "yuki_dossier_transfer_export", {"export_map": "/tmp/x"})
    assert [e for e, _ in seen] == ["pre_call", "post_call", "on_export"]
    assert seen[-1][1]["export_dir"] == "/tmp/x"
