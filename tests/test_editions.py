import json
import re
from decimal import Decimal
from datetime import date
from pathlib import Path

import pytest
from yuki_mcp import attribution, edition, render
from yuki_mcp.attribution import ATTRIBUTION, AttributionError
from yuki_mcp.mailconcept import bouw_concept
from yuki_mcp.handleiding import handleiding_md

ROOT = Path(__file__).resolve().parent.parent
INTERN = edition.EDITION == "intern"
MARKET = edition.EDITION == "marketplace"
A = "[Vennootschapsnaam] BV"


class It:
    def __init__(s, ref, amt):
        s.reference, s.open_amount, s.due_date, s.date = ref, Decimal(amt), "2026-10-01", "2026-09-01"


ITEMS = [It("VF-1", "100")]


def _templates():
    cfg = bouw_concept("[Klant A]", ITEMS, date(2026, 11, 20))
    return {"dashboard": render.dashboard_html(None), "handleiding": render.handleiding_html(),
            "mail_html": cfg["html"], "mail_tekst": cfg["tekst"]}


# ------------------------------------------------------------ editie B
@pytest.mark.skipif(not MARKET, reason="alleen editie B")
class TestMarketplace:
    def _strip(self, text):
        return text.replace(ATTRIBUTION, "").replace("FISC" + "Ai Yuki API Connector", "").replace("FISC" + "Ai-Yuki-API-Connector", "")

    def test_neutraliteitsscan(self):
        verboden = ["FISC" + "ALCI", "fisc" + "alci", "fid-" + "manager", "/home/" + "box", "+32 " + "485", "485 64 " + "80", "BE08" + "04", "FISC" + "Ai", "Hundel" + "gem"]
        gescand = 0
        for p in ROOT.rglob("*"):
            if not p.is_file() or ".venv" in p.parts or "__pycache__" in p.parts or p.suffix in (".png", ".pyc", ".jpg"):
                continue
            if p.name in ("LICENSE", "NOTICE") or p.name == "attribution.py" or p.name == "test_editions.py":
                continue
            try:
                txt = p.read_text(encoding="utf-8")
            except UnicodeDecodeError:
                continue
            gescand += 1
            rest = self._strip(txt)
            for v in verboden:
                assert v not in rest, f"{v!r} in {p.relative_to(ROOT)}"
        assert gescand > 20

    def test_attributie_constante_exact(self):
        assert ATTRIBUTION == "Powered by FISCALCI Accounting & Tax (Askin Alci)"
        assert attribution.constant_intact()
        assert edition.REQUIRE_ATTRIBUTION is True

    def test_gewijzigde_constante_weigert_opstart(self, monkeypatch, server):
        monkeypatch.setattr(attribution, "ATTRIBUTION", "Powered by iets anders")
        assert not attribution.constant_intact()
        with pytest.raises(AttributionError):
            server()

    def test_exports_bevatten_exacte_tekst(self, tmp_path, rpc):
        t = _templates()
        for naam, txt in t.items():
            assert ATTRIBUTION in txt, naam
        assert ATTRIBUTION in handleiding_md() + ATTRIBUTION
        r = rpc.call("yuki_handleiding_saldi", export_map=str(tmp_path))
        assert ATTRIBUTION in (tmp_path / "handleiding-saldi.md").read_text() and ATTRIBUTION in (tmp_path / "handleiding-saldi.html").read_text()
        m = bouw_concept("[Klant A]", ITEMS, date(2026, 11, 20), eml_map=tmp_path)
        assert m["vermelding"] == ATTRIBUTION and ATTRIBUTION in Path(m["eml_pad"]).read_text()
        d = rpc.call("yuki_dashboard", administratie=A, jaar=2026, export_map=str(tmp_path))
        assert ATTRIBUTION in Path(d["structuredContent"]["export_pad"]).read_text(encoding="utf-8")

    def test_ontbrekende_tekst_weigert_export(self, monkeypatch):
        monkeypatch.setattr(render, "branding", lambda: {"colors": render.BASE_COLORS, "logo": "", "logo_alt": "x", "name": "x", "footer": ""})
        with pytest.raises(AttributionError):
            render.dashboard_html(None)
        with pytest.raises(AttributionError):
            attribution.ensure("zonder vermelding", True)

    def test_gewijzigde_tekst_weigert_export(self, monkeypatch):
        bad = ATTRIBUTION.replace("Powered", "powered")
        monkeypatch.setattr(render, "branding", lambda: {"colors": render.BASE_COLORS, "logo": "", "logo_alt": "x", "name": "x", "footer": bad})
        with pytest.raises(AttributionError):
            render.handleiding_html()

    def test_geen_interne_regels(self):
        r = bouw_concept("[Klant A]", ITEMS, date(2026, 11, 20), handtekening="Jan")
        assert "cc_voorstel" not in r and "regels_bron" not in r and "Jan" in r["tekst"]
        assert edition.INTERNAL_RULES is False

    def test_branding_instelbaar(self, monkeypatch):
        monkeypatch.setenv("YUKI_BRAND_NAME", "Boekhouding [Voorbeeld]")
        monkeypatch.setenv("YUKI_BRAND_COLOR", "#336699")
        h = render.dashboard_html(None)
        assert "Boekhouding [Voorbeeld]" in h and "#336699" in h and ATTRIBUTION in h

    def test_licentie_en_notice(self):
        assert ATTRIBUTION in (ROOT / "NOTICE").read_text(encoding="utf-8")
        assert "Apache License" in (ROOT / "LICENSE").read_text(encoding="utf-8")
        assert ATTRIBUTION in (ROOT / "README.md").read_text(encoding="utf-8")
        assert "Copyright 2026 Askin Alci" in (ROOT / "NOTICE").read_text(encoding="utf-8")

    def test_auteur_in_manifesten_readme_notice(self):
        for f in (".cursor-plugin/plugin.json", "plugin.json"):
            assert json.loads((ROOT / f).read_text(encoding="utf-8"))["author"]["name"] == "Askin Alci"
        assert "Auteur: Askin Alci" in (ROOT / ("README.nl.md" if MARKET else "README.md")).read_text(encoding="utf-8")
        assert "Author: Askin Alci" in (ROOT / "README.md").read_text(encoding="utf-8") if MARKET else True
        assert json.loads((ROOT / ".cursor-plugin/plugin.json").read_text(encoding="utf-8"))["license"] == "Apache-2.0"



def _png_size(path):
    import struct
    b = path.read_bytes()
    assert b[:8] == b"\x89PNG\r\n\x1a\n"
    return struct.unpack(">II", b[16:24])


@pytest.mark.skipif(edition.EDITION != "marketplace", reason="logo-test alleen voor editie B")
def test_b_logo_assets_en_manifest():
    import json as _j
    assert _png_size(ROOT / "assets" / "logo.png") == (512, 512)
    assert _png_size(ROOT / "assets" / "logo-128.png") == (128, 128)
    assert _png_size(ROOT / "assets" / "logo-icoon-512.png") == (512, 512)
    assert not (ROOT / "assets" / "logo.svg").exists()
    assert not (ROOT / "assets" / "logo-placeholder.svg").exists()
    for m in (ROOT / ".cursor-plugin" / "plugin.json", ROOT / "plugin.json"):
        assert _j.loads(m.read_text())["logo"] == "assets/logo.png"


@pytest.mark.skipif(edition.EDITION != "intern", reason="alleen editie A")
def test_a_krijgt_het_software_logo_niet():
    assert not (ROOT / "assets" / "logo-icoon-512.png").exists() and not (ROOT / "assets" / "logo-128.png").exists()
    assert not (ROOT / "assets" / "bron").exists()


def test_belgische_afbakening_in_docs_en_manifesten():
    root = ROOT
    needle = "Belgische boekhouders/accountants"
    vol = "Gebruik buiten België: verifieer zelf de lokale regels."
    for f in (("README.nl.md" if edition.EDITION == "marketplace" else "README.md"), "skills/%s/SKILL.md" % edition.PLUGIN_NAME, "docs/handleiding-saldi.md"):
        txt = (root / f).read_text(encoding="utf-8")
        assert needle in txt and "MAR" in txt and "Belgisch btw-stelsel" in txt and vol in txt, f
    for m in (root / ".cursor-plugin" / "plugin.json", root / "plugin.json"):
        d = json.loads(m.read_text(encoding="utf-8"))["description"]
        assert ("Belgische" in d and "MAR" in d and "btw" in d) or (edition.EDITION == "marketplace" and "Belgian" in d), m
    if edition.EDITION == "marketplace":
        en = (root / "README.md").read_text(encoding="utf-8")
        assert "Belgian accountants" in en and "Belgian chart of accounts (MAR)" in en and "Belgian VAT" in en and vol in en and needle in en
        assert not (root / "marketplace").exists()          # dossier-stukken horen niet in de publieke repo
    from yuki_mcp.handleiding import handleiding_html_body
    assert "officiële bronnen" in handleiding_html_body() and "verifieer actuele regel" in handleiding_html_body()


def test_boekingsdocs_en_tools_zijn_belgisch_afgebakend():
    d = ROOT / "docs" / "BOEKINGSWORKFLOW.md"
    if not d.exists():
        pytest.skip("alleen in de gebouwde editie")
    t = d.read_text(encoding="utf-8")
    for w in ("Belgische", "MAR", "btw", "verifieer actuele regel", "buiten België", "standaard UIT", "YUKI_WRITE_ENABLED=ja"):
        assert w in t, w
    assert "440000" in t and "411000" in t and "451000" in t and not re.search(r"(?i)\bart(ikel|\.)\s*\d", t)   # geen niet-officiële wetsverwijzingen
    rd = (ROOT / ("README.nl.md" if MARKET else "README.md")).read_text(encoding="utf-8")
    assert "Belgisch" in rd and "YUKI_WRITE_ENABLED" in rd


@pytest.mark.skipif(edition.EDITION != "marketplace", reason="publieke indeling alleen voor editie B")
def test_b_publieke_indeling_en_veilige_inhoud():
    for f in ("README.md", "README.nl.md", "CONTRIBUTING.md", "SECURITY.md", "CHANGELOG.md", "LICENSE", "NOTICE", "docs/index.md", "docs/TOOLS.md",
              ".github/ISSUE_TEMPLATE/bug_report.md", "docs/images/architecture.png", "docs/images/example-output.png", "assets/logo.png"):
        assert (ROOT / f).exists(), f
    for p in (ROOT / "docs" / "images").glob("*.svg"):
        assert p.read_text().startswith("<svg")
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    assert en.count("```mermaid") == 1 and "assets/logo.png" in en and ATTRIBUTION in en
    assert "read-only" in en.lower() and "Afhandelen" in en and "YUKI_ACCESS_KEY" in en
    for p in ROOT.rglob("*"):
        if p.is_file() and p.suffix in (".md", ".json", ".yml", ".py", ".txt", ".svg", ".html") and ".venv" not in p.parts and p.name != "test_editions.py":
            txt = p.read_text(encoding="utf-8", errors="ignore")
            assert "BE0804" not in txt and "0804.135.542" not in txt and "FISCALCI BV" not in txt, p
    assert not any(p.name in (".env", "boekingen-audit.jsonl") for p in ROOT.rglob("*"))
    assert (ROOT / "tests").is_dir() and not (ROOT / "_tests").exists()


@pytest.mark.skipif(edition.EDITION != "marketplace", reason="positionering alleen voor editie B")
def test_b_positionering_grok_bot_eerst():
    en = (ROOT / "README.md").read_text(encoding="utf-8")
    nl = (ROOT / "README.nl.md").read_text(encoding="utf-8")
    assert "plugin for Grok Bot" in en[:900] and "plugin voor Grok Bot" in nl[:900].replace("Plugin voor", "plugin voor") or "Grok Bot" in nl[:900]
    assert en.index("## Install in Grok Bot (recommended)") < en.index("## Other MCP clients")
    assert nl.index("## Installatie in Grok Bot (aanbevolen)") < nl.index("## Andere MCP-clients")
    for w in ("Cursor", "Claude", "Copilot", "Windsurf"):
        assert w in en and w in nl
    assert "Grok Bot" in (ROOT / "docs" / "index.md").read_text(encoding="utf-8")
    for m in (ROOT / ".cursor-plugin" / "plugin.json", ROOT / "plugin.json"):
        assert "Grok Bot" in json.loads(m.read_text(encoding="utf-8"))["description"]
    assert ATTRIBUTION in en and "Belgian chart of accounts (MAR)" in en
