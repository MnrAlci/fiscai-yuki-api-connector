"""Editie B: voorbeelden, handleidingen, links en afbeeldingen."""
import csv
import json
import py_compile
import re
try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib
from pathlib import Path

import pytest
from yuki_mcp import edition, export as exp

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(edition.EDITION != "marketplace", reason="alleen editie B")
SECRET_PATTERNS = [r"am_[A-Za-z0-9]{10,}", r"\b[0-9a-f]{32,}\b", r"[A-Za-z0-9+/]{40,}={0,2}", r"sk-[A-Za-z0-9]{16,}", r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"]
OK_VALUE = re.compile(r"^(\$\{[A-Za-z_:\-]+\}|\$\{(env|input):[A-Za-z_\-]+\}|YOUR_[A-Z_]+|domein|portaal|[A-Za-z0-9 _\-,./]*)$")


def _examples():
    return sorted(p for p in (ROOT / "examples").rglob("*") if p.is_file())


def test_voorbeeldconfigs_parsen_en_bevatten_geen_geheimen():
    n = 0
    for p in _examples():
        text = p.read_text(encoding="utf-8")
        for pat in SECRET_PATTERNS:
            assert not re.search(pat, text), (p.name, pat)
        assert not re.search(r"YUKI_WRITE_ENABLED[\"']?\s*[:=]\s*[\"']?ja", text), p.name
        if p.suffix == ".json" and p.parent.name == "examples":
            cfg = json.loads(text)
            n += 1
            servers = cfg.get("mcpServers") or cfg.get("servers") or cfg["mcp"]["servers"]
            for name, s in servers.items():
                for k, v in (s.get("env") or {}).items():
                    assert OK_VALUE.match(str(v)), (p.name, k)
                for k, v in (s.get("headers") or {}).items():
                    assert re.match(r"^\$\{(env:)?[A-Z_]+\}$", v), (p.name, k)
                assert "command" in s or "url" in s
        if p.suffix == ".yaml":
            try:
                import yaml  # type: ignore
                cfg = yaml.safe_load(text)
                assert "fiscai-yuki-api-connector" in cfg["mcp_servers"]
            except ImportError:
                assert "mcp_servers:" in text and "${YUKI_ACCESS_KEY}" in text
        if p.suffix == ".py":
            py_compile.compile(str(p), cfile=str(Path("/tmp") / (p.name + "c")), doraise=True)
    assert n >= 8


def test_voorbeeldmatrix_en_dataschema():
    for ds in exp.SCHEMAS:
        with open(ROOT / "examples" / "data" / f"yuki-{ds}.csv", encoding="utf-8") as f:
            rd = csv.DictReader(f)
            assert rd.fieldnames == exp.cols(ds)
            rows = list(rd)
        assert rows and all("[Voorbeeld]" in r["administratie"] for r in rows)
        js = json.loads((ROOT / "examples" / "data" / f"yuki-{ds}.json").read_text(encoding="utf-8"))
        assert js["voorbeeld"] is True and len(js["rijen"]) == len(rows)
    doc = (ROOT / "docs" / "EXPORT-SCHEMA.md").read_text(encoding="utf-8")
    for ds in exp.SCHEMAS:
        for c in exp.cols(ds):
            assert f"`{c}`" in doc


def test_pyproject():
    d = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert d["project"]["scripts"]["yuki-api-connector"] == "yuki_mcp.cli:main"
    assert d["project"]["license"] == "Apache-2.0"                  # SPDX-expressie (PEP 639)
    assert {"LICENSE", "NOTICE"} <= set(d["project"]["license-files"])


def test_relatieve_links_en_afbeeldingen_bestaan():
    bad = []
    for md in list(ROOT.rglob("*.md")):
        if "tests" in md.parts or ".github" in md.parts:
            continue
        for m in re.finditer(r"\]\(([^)\s]+)\)", md.read_text(encoding="utf-8")):
            t = m.group(1).split("#")[0]
            if not t or re.match(r"^(https?:|mailto:|<)", t):
                continue
            if not (md.parent / t).resolve().exists():
                bad.append((str(md.relative_to(ROOT)), t))
    assert not bad, bad[:15]


def test_alle_nieuwe_gidsen_hebben_vermelding_en_melding_en_alle_tools_staan_in_de_docs():
    attr = "Powered by FISCALCI Accounting & Tax (Askin Alci)"
    for md in (ROOT / "docs").rglob("*.md"):
        if md.name in ("TOOLS.md", "INVENTARIS-LEESMETHODES.md", "handleiding-saldi.md", "BOEKINGSWORKFLOW.md", "index.md"):
            continue
        t = md.read_text(encoding="utf-8")
        assert attr in t, md
    tools = (ROOT / "docs" / "TOOLS.md").read_text(encoding="utf-8")
    for n in ("yuki_dashboard_kpis", "yuki_portfolio_kpis", "yuki_export_dataset"):
        assert n in tools


def test_aantallen_en_dekking():
    assert len([p for p in (ROOT / "docs/integrations/visualisatie").glob("*.md")]) >= 14      # 13 + index
    assert len([p for p in (ROOT / "docs/integrations/documenten").glob("*.md")]) == 11        # 10 + index
    rows = [l for l in (ROOT / "docs/integrations/APPS.md").read_text(encoding="utf-8").splitlines() if l.startswith("| ") and "](http" in l]
    assert len(rows) >= 40
    for name in ("Power BI", "Qlik Sense", "Domo", "Looker", "Tableau", "Lovable", "Metabase", "Superset", "Grafana", "Streamlit", "Dash", "Hex", "Snowflake"):
        assert name in (ROOT / "docs/integrations/visualisatie/README.md").read_text(encoding="utf-8")
    for name in ("Zapier", "Make", "n8n", "Power Automate", "Pipedream", "IFTTT"):
        assert name in (ROOT / "docs/integrations/automatisering/README.md").read_text(encoding="utf-8")
    assert "GDPR" in (ROOT / "docs/integrations/gegevensverzameling/README.md").read_text(encoding="utf-8")
    snow = (ROOT / "docs/integrations/visualisatie/snowflake.md").read_text(encoding="utf-8")
    assert "PAID" in snow
    for f in ("README.md", "README.nl.md"):
        t = (ROOT / f).read_text(encoding="utf-8")
        for key in ("Hermes", "OpenClaw", "AgentMail", "APPS.md", "EXPORT-SCHEMA.md"):
            assert key in t, (f, key)
    idx = (ROOT / "docs/index.md").read_text(encoding="utf-8")
    assert "APPS.md" in idx and "documenten" in idx
    assert "yuki_export_dataset" in (ROOT / "CHANGELOG.md").read_text(encoding="utf-8")


def test_afbeeldingen_in_gidsen_bestaan_en_zijn_png():
    imgs = list((ROOT / "docs/images/guides").glob("*.png"))
    assert len(imgs) >= 16
    for p in imgs + [ROOT / "docs/images/business-dashboard-example.png", ROOT / "docs/images/portfolio-dashboard-example.png", ROOT / "docs/images/export-layer.png"]:
        assert p.read_bytes()[:8] == b"\x89PNG\r\n\x1a\n" and p.stat().st_size > 3000, p
