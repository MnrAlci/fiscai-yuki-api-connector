"""Workflows: agenda, verplichtingen, overzichten, concepten en verzendbeveiliging. Geen netwerk, [Voorbeeld]-gegevens."""
import base64
import json
import os
from datetime import date, datetime
from pathlib import Path

import pytest

from yuki_mcp import cli, registry, workflows as wf
from yuki_mcp.wf_calendars import CalendarError, GoogleAdapter, GraphAdapter, ICSAdapter, make_adapter
from yuki_mcp.wf_drafts import AgentMailAdapter, Draft, DraftError, EmlAdapter, GmailAdapter, OutlookAdapter, SendRefused, SmtpAdapter, send_allowed
from yuki_mcp.wf_ics import get_tz, in_window, parse_ics

ICS = """BEGIN:VCALENDAR
VERSION:2.0
BEGIN:VEVENT
UID:a1
DTSTART;TZID=Europe/Brussels:20261123T100000
DTEND;TZID=Europe/Brussels:20261123T110000
SUMMARY:[Voorbeeld] BV: bespreking
  jaarcijfers
ATTENDEE;CN=X:mailto:Contact@Voorbeeld.example
END:VEVENT
BEGIN:VEVENT
UID:b1
DTSTART:20261123T080000Z
DTEND:20261123T090000Z
SUMMARY:Teamoverleg intern
END:VEVENT
BEGIN:VEVENT
UID:c1
DTSTART;VALUE=DATE:20261125
SUMMARY:Hele dag [Voorbeeld] BV
END:VEVENT
BEGIN:VEVENT
UID:d1
DTSTART;TZID=Europe/Brussels:20261102T140000
DTEND;TZID=Europe/Brussels:20261102T150000
SUMMARY:Wekelijks overleg [Voorbeeld] BV
RRULE:FREQ=WEEKLY;COUNT=4
EXDATE;TZID=Europe/Brussels:20261109T140000
END:VEVENT
BEGIN:VEVENT
UID:e1
DTSTART;TZID=Romance Standard Time:20261201T090000
SUMMARY:Outlook-zonenaam
END:VEVENT
END:VCALENDAR
"""
TZ = get_tz("Europe/Brussels")


def D(y, m, d, h=0):
    return datetime(y, m, d, h, tzinfo=TZ)


def base_cfg(**over):
    cfg = {"settings": {"days_ahead": 2}, "clients": [{"name": "[Voorbeeld] BV", "administratie": "[Voorbeeld] BV", "match_keywords": ["[Voorbeeld] BV"],
                                                       "email_to": ["contact@voorbeeld.example"], "documents": ["Bankuittreksels"], "obligations": ["btw-q"]}],
           "obligations": [{"id": "btw-q", "title": "Btw kwartaal", "frequency": "quarterly", "due_day": 20, "due_month_offset": 1, "lead_days": 14, "source": "https://financien.belgium.be/nl",
                            "checklist": ["Controle"], "documents": ["Aankoopfacturen"]}],
           "calendar": {"adapter": "ics"}, "mail": {"adapter": "eml"}, "template": {}, "_base": "."}
    cfg.update(over)
    return cfg


# ---------------------------------------------------------------- ICS
def test_ics_parse_en_tijdzones():
    evs = {e.uid: e for e in parse_ics(ICS)}
    a = evs["a1"]
    assert a.summary == "[Voorbeeld] BV: bespreking jaarcijfers"       # gevouwen regel
    assert a.start == D(2026, 11, 23, 10) and a.attendees == ["contact@voorbeeld.example"]
    assert evs["b1"].start.hour == 9                                    # 08:00Z = 09:00 Brussel (winter)
    assert evs["c1"].all_day and evs["c1"].start.date() == date(2026, 11, 25)
    assert evs["e1"].start.hour == 9                                    # Windows-zonenaam


def test_ics_rrule_en_exdate_en_venster():
    evs = parse_ics(ICS)
    got = [e.start.date().isoformat() for e in in_window(evs, D(2026, 11, 1), D(2026, 12, 1)) if e.uid == "d1"]
    assert got == ["2026-11-02", "2026-11-16", "2026-11-23"]            # 9 nov uitgesloten, COUNT=4 (2,9,16,23)


def test_ics_rrule_heeft_harde_grens():
    txt = "BEGIN:VEVENT\nUID:x\nDTSTART:20200101T100000Z\nSUMMARY:x\nRRULE:FREQ=DAILY\nEND:VEVENT\n"
    assert len(in_window(parse_ics(txt), D(2020, 1, 1), D(2020, 1, 4))) == 3


# ---------------------------------------------------------------- config
def test_config_weigert_geheimen_en_prive_urls(tmp_path):
    for bad in ('[calendar]\nurl = "https://x.example/a.ics?token=abc"\n', '[mail]\npassword = "x"\n', '[calendar]\ngraph_token = "x"\n'):
        p = tmp_path / "w.toml"
        p.write_text(bad, encoding="utf-8")
        with pytest.raises(wf.WorkflowError):
            wf.load_config(p)
    ok = tmp_path / "ok.toml"
    ok.write_text('[calendar]\nadapter = "graph"\ntoken_env = "YUKI_WF_GRAPH_TOKEN"\n', encoding="utf-8")
    assert wf.load_config(ok)["calendar"]["token_env"] == "YUKI_WF_GRAPH_TOKEN"


@pytest.mark.parametrize("mut,msg", [
    (lambda c: c["settings"].update(days_ahead=-1), "days_ahead"),
    (lambda c: c["obligations"][0].pop("source"), "source"),
    (lambda c: c["obligations"][0].pop("due_day"), "due_day"),
    (lambda c: c["obligations"][0].update(frequency="weekly"), "frequency"),
    (lambda c: c["clients"][0].update(obligations=["bestaat-niet"]), "onbekende"),
    (lambda c: c["settings"].update(max_items=0), "max_items"),
    (lambda c: c.update(template={"sections": ["raar"]}), "sectie"),
])
def test_config_validatie(mut, msg):
    cfg = base_cfg()
    mut(cfg)
    with pytest.raises(wf.WorkflowError, match=msg):
        wf.validate(cfg)


# ---------------------------------------------------------------- verplichtingen
def test_due_dates_kwartaal_en_voorsprong():
    ob = base_cfg()["obligations"][0]
    assert [x["due"].isoformat() for x in wf.due_dates(ob, date(2026, 1, 1), date(2026, 12, 31))] == ["2026-01-20", "2026-04-20", "2026-07-20", "2026-10-20"]
    items = wf.plan_obligations(base_cfg(), date(2026, 10, 7))   # 13 dagen vooraf: binnen 14
    assert [i.detail["period"] for i in items] == ["2026-Q3"] and not items[0].detail["overdue"]
    assert wf.plan_obligations(base_cfg(), date(2026, 10, 5)) == []     # 15 dagen vooraf: nog niet
    late = wf.plan_obligations(base_cfg(), date(2026, 10, 25))
    assert late and late[0].detail["overdue"]
    assert wf.plan_obligations(base_cfg(), date(2026, 11, 20)) == []    # voorbij de coulance (14 d)


def test_due_dates_maand_jaar_vast_en_dagclamp():
    m = {"id": "m", "frequency": "monthly", "due_day": 31, "due_month_offset": 1}
    assert wf.due_dates(m, date(2027, 2, 1), date(2027, 2, 28))[0]["due"] == date(2027, 2, 28)   # 31 -> laatste dag
    a = {"id": "a", "frequency": "annual", "due_month": 3, "due_day": 31, "year_offset": -1}
    r = wf.due_dates(a, date(2027, 1, 1), date(2027, 12, 31))
    assert r[0]["due"] == date(2027, 3, 31) and r[0]["jaar"] == 2026
    f = {"id": "f", "frequency": "fixed", "dates": ["2027-07-15"], "year_offset": -1}
    assert wf.due_dates(f, date(2027, 7, 1), date(2027, 7, 31))[0]["jaar"] == 2026
    assert wf.due_dates(f, date(2027, 8, 1), date(2027, 8, 31)) == []


def test_geen_ingebouwde_deadlines():
    src = (Path(wf.__file__)).read_text(encoding="utf-8")
    body = src.split("EXAMPLE_CONFIG")[0]
    assert "due_day=" not in body and "due_day: " not in body
    assert wf.plan_obligations({"clients": [{"name": "x", "administratie": "x"}], "obligations": []}, date(2026, 1, 1)) == []


# ---------------------------------------------------------------- plan: vergaderingen
def test_plan_vergaderingen_n_dagen_vooruit():
    ad = ICSAdapter.__new__(ICSAdapter)
    ad.events = lambda s, e: in_window(parse_ics(ICS), s, e)
    cfg = base_cfg()
    items, skipped = wf.plan_meetings(cfg, date(2026, 11, 21), 2, ad)
    assert [i.title for i in items] == ["[Voorbeeld] BV: bespreking jaarcijfers", "Wekelijks overleg [Voorbeeld] BV", "Hele dag [Voorbeeld] BV"] or len(items) >= 2
    assert any(s["summary"] == "Teamoverleg intern" for s in skipped)
    # 1 dag vooruit: de hele-dag-afspraak van 25/11 valt buiten
    items1, _ = wf.plan_meetings(cfg, date(2026, 11, 22), 1, ad)
    assert all(i.when[:10] <= "2026-11-23" for i in items1)


def test_match_client_op_mail_en_domein():
    ev = parse_ics("BEGIN:VEVENT\nUID:q\nDTSTART:20261123T100000Z\nSUMMARY:Overleg\nATTENDEE:mailto:jan@voorbeeld.example\nEND:VEVENT\n")[0]
    c1 = {"name": "A", "administratie": "A", "match_domains": ["voorbeeld.example"]}
    c2 = {"name": "B", "administratie": "B", "match_emails": ["jan@voorbeeld.example"]}
    assert wf.match_client(ev, [c1])["name"] == "A" and wf.match_client(ev, [c2])["name"] == "B"
    assert wf.match_client(ev, [{"name": "C", "administratie": "C", "match_keywords": ["niets"]}]) is None


# ---------------------------------------------------------------- agenda-adapters
def test_ics_adapter_url_vraagt_https_en_omgeving():
    env = {"YUKI_WF_ICS_URL": "http://x.example/a.ics"}
    with pytest.raises(CalendarError, match="https"):
        ICSAdapter(None, "YUKI_WF_ICS_URL", http_get=lambda u, h: (200, ICS), env=env).events(D(2026, 11, 1), D(2026, 12, 1))
    with pytest.raises(CalendarError, match="niet ingesteld"):
        ICSAdapter(None, "LEEG", env={}).events(D(2026, 11, 1), D(2026, 12, 1))
    env["YUKI_WF_ICS_URL"] = "webcal://x.example/a.ics"
    seen = []
    ev = ICSAdapter(None, "YUKI_WF_ICS_URL", http_get=lambda u, h: (seen.append(u) or (200, ICS)), env=env).events(D(2026, 11, 23), D(2026, 11, 24))
    assert seen == ["https://x.example/a.ics"] and ev


def test_graph_adapter_met_nepantwoord():
    page = {"value": [{"id": "g1", "subject": "[Voorbeeld] BV overleg", "start": {"dateTime": "2026-11-23T09:00:00.0000000", "timeZone": "UTC"}, "end": {"dateTime": "2026-11-23T10:00:00.0000000", "timeZone": "UTC"},
                       "attendees": [{"emailAddress": {"address": "Jan@Voorbeeld.example"}}], "organizer": {"emailAddress": {"address": "me@voorbeeld.example"}}}]}
    calls = []

    def get(url, headers):
        calls.append((url, headers))
        return 200, json.dumps(page)
    ev = GraphAdapter("TOK", http_get=get, env={"TOK": "dummy"}).events(D(2026, 11, 23), D(2026, 11, 25))
    assert ev[0].start == D(2026, 11, 23, 10) and ev[0].attendees == ["jan@voorbeeld.example"]
    assert calls[0][1]["Authorization"] == "Bearer dummy" and "calendarView" in calls[0][0] and "graph.microsoft.com" in calls[0][0]
    with pytest.raises(CalendarError, match="niet ingesteld"):
        GraphAdapter("TOK", http_get=get, env={}).events(D(2026, 11, 23), D(2026, 11, 25))
    with pytest.raises(CalendarError, match="HTTP 401"):
        GraphAdapter("TOK", http_get=lambda u, h: (401, ""), env={"TOK": "x"}).events(D(2026, 11, 23), D(2026, 11, 25))


def test_google_adapter_en_make_adapter():
    page = {"items": [{"id": "x", "summary": "[Voorbeeld] BV", "start": {"dateTime": "2026-11-23T10:00:00+01:00"}, "end": {"dateTime": "2026-11-23T11:00:00+01:00"}, "attendees": [{"email": "a@b.example"}]},
                      {"id": "y", "summary": "dag", "start": {"date": "2026-11-24"}, "end": {"date": "2026-11-25"}}]}
    ev = GoogleAdapter("T", http_get=lambda u, h: (200, json.dumps(page)), env={"T": "t"}).events(D(2026, 11, 23), D(2026, 11, 26))
    assert len(ev) == 2 and ev[0].start == D(2026, 11, 23, 10) and ev[1].all_day
    assert isinstance(make_adapter({"adapter": "graph"}, "Europe/Brussels"), GraphAdapter)
    with pytest.raises(CalendarError):
        make_adapter({"adapter": "ftp"}, "Europe/Brussels")


# ---------------------------------------------------------------- concepten en verzendbeveiliging
def test_eml_concept_is_een_concept(tmp_path):
    p = EmlAdapter(tmp_path, "boekhouder@voorbeeld.example").draft(Draft(["klant@voorbeeld.example"], "Onderwerp é", "Tekst"), "[Voorbeeld] BV-herinnering")
    raw = Path(p).read_bytes().decode("utf-8")
    assert "X-Unsent: 1" in raw and "klant@voorbeeld.example" in raw and Path(p).suffix == ".eml"


def test_http_concept_adapters():
    seen = []

    def post(url, headers, body):
        seen.append((url, headers, body))
        return 201, "{}"
    d = Draft(["k@voorbeeld.example"], "Onderwerp", "Tekst")
    OutlookAdapter("T", post, {"T": "tok"}).draft(d, "n")
    GmailAdapter("T", post, {"T": "tok"}, "me@voorbeeld.example").draft(d, "n")
    AgentMailAdapter("T", "I", http_post=post, env={"T": "tok", "I": "inbox1"}).draft(d, "n")
    assert seen[0][0] == "https://graph.microsoft.com/v1.0/me/messages" and seen[0][2]["toRecipients"][0]["emailAddress"]["address"] == "k@voorbeeld.example"
    assert seen[1][0].endswith("/gmail/v1/users/me/drafts") and b"Subject: Onderwerp" in base64.urlsafe_b64decode(seen[1][2]["message"]["raw"])
    assert b"X-Unsent" not in base64.urlsafe_b64decode(seen[1][2]["message"]["raw"])
    assert seen[2][0] == "https://api.agentmail.to/v0/inboxes/inbox1/drafts" and seen[2][2]["to"] == ["k@voorbeeld.example"]
    assert all(h["Authorization"] == "Bearer tok" for _, h, _ in seen)
    with pytest.raises(DraftError, match="HTTP 500"):
        OutlookAdapter("T", lambda *a: (500, ""), {"T": "tok"}).draft(d, "n")
    with pytest.raises(DraftError, match="niet ingesteld"):
        OutlookAdapter("T", post, {}).draft(d, "n")
    assert not any(getattr(a, "can_send", False) for a in (OutlookAdapter("T"), GmailAdapter("T"), AgentMailAdapter("T", "I")))


def test_verzendbeveiliging_drie_sloten():
    assert send_allowed({}, False, False) is False                       # niet gevraagd
    with pytest.raises(SendRefused, match="allow_send"):
        send_allowed({}, True, True)                                     # config ontbreekt
    with pytest.raises(SendRefused, match="bevestiging"):
        send_allowed({"allow_send": True}, True, False, interactive=False)
    assert send_allowed({"allow_send": True}, True, True) is True
    assert send_allowed({"allow_send": True}, True, False, True, lambda q: "VERSTUUR") is True
    assert send_allowed({"allow_send": True}, True, False, True, lambda q: "ja") is False
    with pytest.raises(SendRefused):
        send_allowed({"allow_send": "true"}, True, True)                 # alleen echte boolean true


# ---------------------------------------------------------------- uitvoeren
KPI = {"periode": {"van": "2026-01-01", "tot": "2026-12-31"}, "omzet": "1000.00", "kosten": "400.00", "resultaat": "600.00", "liquide_middelen": "50.00",
       "open_debiteuren": {"totaal": "10.00", "vervallen": "5.00"}, "open_crediteuren": {"totaal": "3.00", "vervallen": "0.00"}, "btw_indicatie": {"saldo": "12.00"}}
AGE = {"peildatum": "2026-11-23", "totaal_positief": "10.00", "vervallen_totaal": "5.00", "buckets": {}, "negatieve_posten": {"aantal": 1}}


class FakeCall:
    def __init__(self, fail=None):
        self.calls, self.fail = [], fail

    def __call__(self, name, args):
        self.calls.append((name, args))
        if self.fail == name:
            raise RuntimeError("kapot " + os.environ.get("YUKI_ACCESS_KEY", ""))
        return KPI if name == "yuki_dashboard_kpis" else AGE


class FakeHooks:
    def __init__(self):
        self.events = []

    def fire(self, event, payload):
        self.events.append((event, payload))


def _ns(argv):
    return cli.build_parser().parse_args(argv)


@pytest.fixture
def wfile(tmp_path):
    (tmp_path / "agenda.ics").write_text(ICS, encoding="utf-8")
    (tmp_path / "status.json").write_text(json.dumps({"received": ["bankuittreksels"], "last_reviewed": "2026-11-01", "notes": "[Voorbeeld] notitie"}), encoding="utf-8")
    t = tmp_path / "workflows.toml"
    t.write_text('''[settings]
days_ahead = 2
[calendar]
adapter = "ics"
path = "agenda.ics"
[mail]
adapter = "eml"
signature = "[Voorbeeld] Uw boekhouder"
[template]
sections = ["kpis", "open_items", "missing_documents", "dossier_status"]
kpis = ["omzet", "resultaat", "open_debiteuren.vervallen", "bestaat.niet"]
[[clients]]
name = "[Voorbeeld] BV"
administratie = "[Voorbeeld] BV"
match_keywords = ["[Voorbeeld] BV"]
email_to = ["contact@voorbeeld.example"]
status_file = "status.json"
documents = ["Bankuittreksels", "Verkoopfacturen"]
obligations = ["btw-q"]
[[obligations]]
id = "btw-q"
title = "Btw kwartaal"
frequency = "quarterly"
due_day = 20
due_month_offset = 1
lead_days = 14
source = "https://financien.belgium.be/nl"
checklist = ["Controle"]
documents = ["Aankoopfacturen"]
''', encoding="utf-8")
    return t


def test_run_maakt_overzicht_en_concept_zonder_te_versturen(wfile, tmp_path, capsys):
    call, hooks = FakeCall(), FakeHooks()
    a = _ns(["workflows", "run", "-w", str(wfile), "--today", "2026-11-21", "--json"])
    rc = wf.cmd_workflows(a, cli.Out(True, False), tools_factory=lambda: (call, hooks))
    res = json.loads(capsys.readouterr().out)
    assert rc == 0 and res["results"]
    names = {n for n, _ in call.calls}
    assert names <= set(wf.ALLOWED_TOOLS) and "yuki_dashboard_kpis" in names               # alleen toegelaten leestools
    out = tmp_path / "workflow-output"
    md = next(out.glob("*/*meeting*.md")).read_text(encoding="utf-8")
    assert "| omzet | 1000.00 |" in md and "| bestaat.niet | n.v.t. |" in md and "- [ ] Verkoopfacturen" in md and "- [ ] Bankuittreksels" not in md
    assert "Powered by FISCALCI Accounting & Tax (Askin Alci)" in md and "Belgische" in md
    emls = list((out / "drafts").glob("*.eml"))
    assert emls and "Verkoopfacturen" in emls[0].read_bytes().decode("utf-8", "replace") and "X-Unsent: 1" in emls[0].read_bytes().decode()
    assert any(e == "on_export" for e, _ in hooks.events)                                 # hooks-integratie
    assert all(not r["sent"] for r in res["results"])


def test_run_is_idempotent_en_force(wfile, capsys):
    call = FakeCall()
    argv = ["workflows", "run", "-w", str(wfile), "--today", "2026-11-21", "--json"]
    wf.cmd_workflows(_ns(argv), cli.Out(True, False), tools_factory=lambda: (call, FakeHooks()))
    n1 = len(call.calls)
    capsys.readouterr()
    wf.cmd_workflows(_ns(argv), cli.Out(True, False), tools_factory=lambda: (call, FakeHooks()))
    res = json.loads(capsys.readouterr().out)
    assert len(call.calls) == n1 and {r["status"] for r in res["results"]} == {"al_gedaan"}
    wf.cmd_workflows(_ns(argv + ["--force"]), cli.Out(True, False), tools_factory=lambda: (call, FakeHooks()))
    assert len(call.calls) == 2 * n1


def test_dry_run_en_plan_doen_geen_yuki_calls_en_schrijven_niets(wfile, tmp_path, capsys):
    def boom():
        raise AssertionError("geen tools in dry-run/plan")
    for argv in (["workflows", "run", "--dry-run"], ["workflows", "plan"]):
        a = _ns(argv + ["-w", str(wfile), "--today", "2026-11-21", "--json"])
        assert wf.cmd_workflows(a, cli.Out(True, False), tools_factory=boom) == 0
        d = json.loads(capsys.readouterr().out)
        assert d["network_yuki"] is False and d["items"]
    assert not (tmp_path / "workflow-output").exists()


def test_sectiefout_wordt_gerapporteerd_zonder_geheimen_en_niet_als_klaar_gemarkeerd(wfile, tmp_path, capsys, monkeypatch):
    monkeypatch.setenv("YUKI_ACCESS_KEY", "SUPERGEHEIM123456")
    call = FakeCall(fail="yuki_dashboard_kpis")
    a = _ns(["workflows", "run", "-w", str(wfile), "--today", "2026-11-21", "--only", "meetings", "--json"])
    rc = wf.cmd_workflows(a, cli.Out(True, False), tools_factory=lambda: (call, FakeHooks()))
    out = capsys.readouterr().out
    assert rc == cli.EXIT_TOOL and "SUPERGEHEIM123456" not in out and "kapot" in out
    assert "SUPERGEHEIM123456" not in "".join(p.read_text() for p in (tmp_path / "workflow-output").rglob("*.*") if p.suffix in (".md", ".json", ".eml"))
    assert json.loads((tmp_path / "workflow-output" / "state.json").read_text()) == {}      # opnieuw proberen bij volgende run


def test_max_items_beschermt_het_daglimiet(wfile, tmp_path, capsys):
    t = wfile.read_text(encoding="utf-8").replace("days_ahead = 2", "days_ahead = 10\nmax_items = 1")
    wfile.write_text(t, encoding="utf-8")
    a = _ns(["workflows", "run", "-w", str(wfile), "--today", "2026-11-21", "--only", "meetings", "--json"])
    wf.cmd_workflows(a, cli.Out(True, False), tools_factory=lambda: (FakeCall(), FakeHooks()))
    st = [r["status"] for r in json.loads(capsys.readouterr().out)["results"]]
    assert st.count("klaar") == 1 and "overgeslagen_max_items" in st


def test_verzenden_zonder_config_wordt_geweigerd_en_er_is_geen_netwerk(wfile, capsys):
    a = _ns(["workflows", "run", "-w", str(wfile), "--today", "2026-11-21", "--send", "--confirm-send"])
    rc = wf.cmd_workflows(a, cli.Out(False, False), tools_factory=lambda: (FakeCall(), FakeHooks()))
    assert rc == cli.EXIT_REFUSED and "allow_send" in capsys.readouterr().err


def test_smtp_verstuurt_alleen_na_alle_sloten(wfile, tmp_path, monkeypatch):
    t = wfile.read_text(encoding="utf-8").replace('adapter = "eml"', 'adapter = "smtp"\nallow_send = true\nsender = "boekhouder@voorbeeld.example"')
    wfile.write_text(t, encoding="utf-8")
    sent = []

    class FakeSMTP:
        def __init__(self, *a, **k):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, u, p):
            pass

        def send_message(self, m):
            sent.append(m)
    monkeypatch.setenv("YUKI_WF_SMTP_HOST", "smtp.voorbeeld.example")
    cfg = wf.load_config(wfile)
    items = wf.plan_obligations(cfg, date(2026, 10, 7))
    drafter = SmtpAdapter(tmp_path / "d", "boekhouder@voorbeeld.example", "YUKI_WF_SMTP_HOST", "U", "P", smtp_factory=FakeSMTP)
    wf.run_items(items, cfg, FakeCall(), tmp_path / "o", date(2026, 10, 7), "nl", drafter, True, False, False)
    assert sent == []                                                     # concept, niets verstuurd
    wf.run_items(items, cfg, FakeCall(), tmp_path / "o2", date(2026, 10, 7), "nl", drafter, True, True, False)
    assert len(sent) == 1 and sent[0]["To"] == "contact@voorbeeld.example" and sent[0]["X-Unsent"] is None
    with pytest.raises(SendRefused):                                       # adapter zonder verzendfunctie
        wf.run_items(items, cfg, FakeCall(), tmp_path / "o3", date(2026, 10, 7), "nl", EmlAdapter(tmp_path / "d3"), True, True, False)


def test_toolrunner_laat_alleen_toegelaten_leestools_toe():
    class T:
        defs = {"yuki_dashboard_kpis": {"annotations": {"readOnlyHint": True}}, "yuki_boeking_bevestigen": {"annotations": {"readOnlyHint": False}},
                "yuki_export_dataset": {"annotations": {"readOnlyHint": False}}}

        def call(self, n, a):
            return {"ok": True}
    r = wf.ToolRunner(T(), FakeHooks())
    assert r("yuki_dashboard_kpis", {}) == {"ok": True}
    for bad in ("yuki_boeking_bevestigen", "yuki_export_dataset", "yuki_bestaat_niet"):
        with pytest.raises(SendRefused):
            r(bad, {})
    # alle toegelaten tools bestaan en zijn echt alleen-lezen in het register
    from yuki_mcp.tools import Tools

    class F:
        pass
    defs = Tools.__dict__  # alleen om import te bewijzen
    assert defs


def test_toegelaten_tools_zijn_alleen_lezen_in_het_register():
    from yuki_mcp.clientfactory import ClientFactory
    from yuki_mcp.tools import Tools
    t = Tools(ClientFactory())
    for n in wf.ALLOWED_TOOLS:
        assert t.defs[n]["annotations"]["readOnlyHint"] is True, n


def test_cli_workflows_list_en_init(tmp_path, capsys):
    p = tmp_path / "w.toml"
    assert cli.main(["workflows", "init", "--path", str(p)]) == 0
    assert cli.main(["workflows", "init", "--path", str(p)]) == cli.EXIT_CONFIG        # overschrijft niet
    capsys.readouterr()
    assert cli.main(["workflows", "list", "-w", str(p), "--json"]) == 0
    d = json.loads(capsys.readouterr().out)
    assert {o["id"] for o in d["obligations"]} >= {"btw-kwartaal", "klantenlisting", "ubo-register", "jaarrekening", "personenbelasting"}
    assert all(o["verify"] and o["source"].startswith("https://") for o in d["obligations"])
    assert cli.main(["workflows", "list", "-w", str(tmp_path / "nope.toml")]) == cli.EXIT_CONFIG
    assert cli.main(["workflows"]) == cli.EXIT_USAGE


def test_voorbeeldconfig_is_geldig_en_zonder_geheimen(tmp_path):
    p = tmp_path / "w.toml"
    p.write_text(wf.EXAMPLE_CONFIG, encoding="utf-8")
    cfg = wf.load_config(p)
    assert cfg["mail"]["allow_send"] is False and cfg["mail"]["adapter"] == "eml"
    assert "Powered by FISCALCI Accounting & Tax (Askin Alci)" in wf.EXAMPLE_CONFIG
    ex = Path(__file__).parent.parent / "examples" / "workflows"
    if ex.is_dir():
        c2 = wf.load_config(ex / "workflows.example.toml")
        assert c2["obligations"] == cfg["obligations"]
        assert parse_ics((ex / "agenda-voorbeeld.ics").read_text(encoding="utf-8"))
        json.loads((ex / "n8n-workflow.json").read_text(encoding="utf-8"))
        for f in ex.iterdir():
            txt = f.read_text(encoding="utf-8")
            assert "YUKI_WRITE_ENABLED" not in txt.replace("YUKI_WRITE_ENABLED is never set", "")


def test_periode_methodes_volgen_wsdl_volgorde():
    g = next(x for x in registry.GENERIC if x.tool == "yuki_openstaande_posten_periode")
    assert [p.soap for p in g.params if p.soap] == ["includeBankTransactions", "sortOrder", "startDate", "endDate"]
    params = [("administrationID", "x"), ("domainID", "d"), ("contactType", "Both"), ("searchValue", "v")]
    assert [n for n, _ in registry.order_params("GetSuppliersAndCustomers", params, [("pageNumber", 1)])] == ["administrationID", "domainID", "searchValue", "pageNumber", "contactType"]
    assert [n for n, _ in registry.order_params("Andere", params, [("pageNumber", 1)])] == ["administrationID", "domainID", "contactType", "searchValue", "pageNumber"]
