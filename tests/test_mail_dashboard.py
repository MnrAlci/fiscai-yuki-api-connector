import ast
import email
import email.policy
import json
import re
from datetime import date
from decimal import Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest
from yuki_mcp import edition
from yuki_mcp.mailconcept import bouw_concept, eur

SRC = Path(__file__).resolve().parent.parent / "server" / "yuki_mcp"
A = "[Vennootschapsnaam] BV"


class It:
    def __init__(s, ref, amt, due, d="2026-09-01"):
        s.reference, s.open_amount, s.due_date, s.date = ref, Decimal(str(amt)), due, d


ITEMS = [It("VF-1", "1234.5", "2026-10-01"), It("VF-2", "100", "2026-11-01"), It("CN-1", "-40", None)]


def test_eur_belgische_notatie():
    assert eur(Decimal("1234.5")) == "€ 1.234,50" and eur(Decimal("-40")) == "-€ 40,00"


def test_concept_inhoud_debiteur():
    r = bouw_concept("[Klant A]", ITEMS, date(2026, 11, 20), "debiteuren")
    assert r["status"] == "CONCEPT, niet verzonden" and r["bijlage"] is None
    assert r["totaal_openstaand"] == 1334.5 and r["aantal_posten"] == 2 and r["negatieve_posten_totaal"] == -40.0
    assert "VF-1" in r["tekst"] and "€ 1.334,50" in r["tekst"] and "geen schuld" in r["tekst"] and "Netto openstaand" in r["tekst"] and "tegoed" not in r["tekst"].lower()
    assert "<table" in r["html"] and "Met vriendelijke groeten" in r["tekst"]
    assert "negatief bedrag is geen schuld" in r["tekst"] and "betaling" in r["tekst"]      # toelichting in de mail


def test_concept_leverancier_en_je_vorm():
    r = bouw_concept("[Leverancier B]", ITEMS[:2], date(2026, 11, 20), "crediteuren", aanspreekvorm="je")
    assert r["onderwerp"].startswith("Afstemming") and "jouw" not in r["tekst"] and "jou" in r["tekst"]


def test_geen_posten_geeft_fout():
    with pytest.raises(ValueError):
        bouw_concept("x", [], date(2026, 11, 20))


def test_eml_is_concept_zonder_verzendcode(tmp_path):
    r = bouw_concept("[Klant A]", ITEMS, date(2026, 11, 20), eml_map=tmp_path, aan="klant@example.test")
    m = email.message_from_bytes(Path(r["eml_pad"]).read_bytes(), policy=email.policy.default)
    assert m["X-Unsent"] == "1" and m["Subject"] == r["onderwerp"] and m["To"] == "klant@example.test"
    assert len(list(m.iter_attachments())) == 0


FORBIDDEN_IMPORTS = {"smtplib", "requests", "httpx", "urllib", "urllib3", "socket", "subprocess", "http", "ssl", "imaplib",
                     "poplib", "ftplib", "aiosmtplib", "yagmail", "telnetlib", "asyncio", "shutil", "webbrowser"}
FORBIDDEN_CALLS = {"sendmail", "send_message", "starttls", "login", "connect", "system", "popen", "urlopen", "post", "send"}


def test_mailmodule_bevat_geen_verzendcode_ast():
    tree = ast.parse((SRC / "mailconcept.py").read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for n in node.names:
                assert n.name.split(".")[0] not in FORBIDDEN_IMPORTS, n.name
        if isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            assert node.module.split(".")[0] not in FORBIDDEN_IMPORTS, node.module
        if isinstance(node, ast.Attribute):
            assert node.attr not in FORBIDDEN_CALLS, node.attr
        if isinstance(node, ast.Name):
            assert node.id not in FORBIDDEN_CALLS, node.id


def test_mailtool_via_server(rpc, fake, tmp_path):
    fake.responses["OutstandingDebtorItems"] = (
        "<OutstandingItems xmlns=''><Item><Contact>[Klant A]</Contact><Reference>VF-9</Reference><Date>2026-09-01T00:00:00</Date>"
        "<DueDate>2026-10-01T00:00:00</DueDate><OpenAmount>250.00</OpenAmount></Item></OutstandingItems>")
    r = rpc.call("yuki_herinneringsmail", administratie=A, relatie="klant a", soort="debiteuren", peildatum=None, eml_map=str(tmp_path))
    assert r["isError"] is False, r
    d = json.loads(r["content"][0]["text"])
    assert d["totaal_openstaand"] == 250.0 and Path(d["eml_pad"]).exists()
    assert not any(m in fake.methods() for m in ("ProcessJournal", "UploadDocument"))
    miss = rpc.call("yuki_herinneringsmail", administratie=A, relatie="bestaat niet", soort="debiteuren")
    assert miss["isError"] is True


# ------------------------------------------------------------------ dashboard
class Strict(HTMLParser):
    VOID = {"meta", "img", "br", "hr", "input", "link"}

    def __init__(self):
        super().__init__()
        self.stack, self.ids, self.errors = [], set(), []

    def handle_starttag(self, tag, attrs):
        for k, v in attrs:
            if k == "id":
                self.ids.add(v)
        if tag not in self.VOID:
            self.stack.append(tag)

    def handle_endtag(self, tag):
        if not self.stack or self.stack[-1] != tag:
            self.errors.append(f"onverwacht </{tag}>")
        else:
            self.stack.pop()


def test_widget_resource_en_html(rpc):
    lst = rpc.req("resources/list")["result"]["resources"][0]
    assert lst["uri"] == "ui://yuki/dashboard.html" and lst["mimeType"] == "text/html;profile=mcp-app"
    assert lst["_meta"]["ui"]["csp"] == {"connectDomains": [], "resourceDomains": []}
    c = rpc.req("resources/read", {"uri": "ui://yuki/dashboard.html"})["result"]["contents"][0]
    assert c["mimeType"] == "text/html;profile=mcp-app" and c["_meta"]["ui"]["csp"]["connectDomains"] == []
    p = Strict()
    p.feed(c["text"])
    p.close()
    assert not p.errors and not p.stack
    assert {"kpi", "deb", "cred", "btw", "bron"} <= p.ids
    assert "ui/notifications/tool-result" in c["text"] and "http" not in c["text"].replace("http://", "")
    assert not re.search(r"https?://", c["text"])                 # CSP: geen externe bronnen
    assert "fetch(" not in c["text"] and "XMLHttpRequest" not in c["text"]


def test_dashboard_tool_verwijst_naar_widget(rpc):
    t = next(t for t in rpc.req("tools/list")["result"]["tools"] if t["name"] == "yuki_dashboard")
    assert t["_meta"]["ui"]["resourceUri"] == "ui://yuki/dashboard.html"


def test_dashboard_data_en_export(rpc, tmp_path):
    r = rpc.call("yuki_dashboard", administratie=A, jaar=2026, periode="kwartaal:3", export_map=str(tmp_path))
    assert r["isError"] is False, r
    d = r["structuredContent"]
    assert set(d["kerncijfers"]) >= {"omzet", "kosten", "resultaat", "liquide_middelen", "liquiditeit"}
    assert d["debiteuren"]["ouderdom"]["buckets"] and d["crediteuren"]["ouderdom"]["buckets"] and "netto_te_betalen" in d["btw"]
    assert any("GLAccountBalance" in b for b in d["bronnen"])
    html = Path(d["export_pad"]).read_text(encoding="utf-8")
    p = Strict()
    p.feed(html)
    assert not p.errors and 'id="yuki-data"' in html
    payload = re.search(r'<script type="application/json" id="yuki-data">(.*?)</script>', html, re.S).group(1)
    assert json.loads(payload.replace("<\\/", "</"))["administratie"] == A


def test_oude_formulering_negatief_is_tegoed_komt_nergens_meer_voor():
    import pathlib, re as _re
    root = pathlib.Path(__file__).resolve().parents[1]
    bad = _re.compile(r"negatief\s*=\s*(tegoed|creditnota)|een tegoed zoals|Tegoeden \(negatief\)|negatief bedrag is een tegoed|tegoeden_negatief", _re.I)
    hits = []
    for f in list(root.rglob("*.py")) + list(root.rglob("*.md")) + list(root.rglob("*.html")):
        if ".venv" in f.parts or "_tests" in f.parts or "tests" in f.parts or "_build" in f.parts or "vendor" in f.parts:
            continue
        if bad.search(f.read_text(encoding="utf-8", errors="ignore")):
            hits.append(str(f.relative_to(root)))
    assert hits == []


def test_handleiding_noemt_vier_oorzaken_en_acties():
    from yuki_mcp.handleiding import handleiding_md
    md = handleiding_md().lower()
    for w in ("creditnota", "afgepunt", "voorschot", "dubbel", "afpunten", "navragen", "terugbetal", "verreken"):
        assert w in md
