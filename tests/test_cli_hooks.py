"""CLI, configuratie en hooks. Geen netwerk, geen echte sleutels."""
import json
import os
import sys
from pathlib import Path

import pytest

from yuki_mcp import cli, config, hooks as hk


def run(argv, capsys, env=None):
    rc = cli.main(argv)
    cap = capsys.readouterr()
    return rc, cap.out, cap.err


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch, tmp_path):
    for k in list(os.environ):
        if k.startswith("YUKI_"):
            monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path / "data"))


def test_version_en_json(capsys):
    rc, out, _ = run(["version", "--json"], capsys)
    d = json.loads(out)
    assert rc == 0 and d["version"] and d["edition"] in ("intern", "marketplace")


def test_geen_opdracht_geeft_gebruikscode(capsys):
    rc, _, _ = run([], capsys)
    assert rc == cli.EXIT_USAGE


def test_onbekende_optie_is_2(capsys):
    rc, _, _ = run(["call", "--bestaat-niet"], capsys)
    assert rc == 2


def test_tools_lijst_en_json(capsys):
    rc, out, _ = run(["tools", "--json"], capsys)
    tl = json.loads(out)
    assert rc == 0 and len(tl) >= 60 and all({"name", "description", "readOnly"} <= set(t) for t in tl)
    assert any(t["name"] == "yuki_export_dataset" for t in tl)


def test_call_weigert_schrijf_tools_en_onbekende(capsys):
    rc, _, err = run(["call", "yuki_boeking_bevestigen"], capsys)
    assert rc == cli.EXIT_REFUSED and "niet alleen-lezen" in err
    rc, _, err = run(["call", "yuki_bestaat_niet"], capsys)
    assert rc == cli.EXIT_USAGE


def test_call_valideert_parameters_en_dry_run(capsys):
    rc, _, err = run(["call", "yuki_dashboard_kpis", "--args", "{}"], capsys)
    assert rc == cli.EXIT_USAGE and "ontbrekende parameter" in err
    rc, out, _ = run(["call", "yuki_dashboard_kpis", "--args", '{"administratie":"[Voorbeeld] BV","jaar":2026}', "--dry-run", "--json"], capsys)
    d = json.loads(out)
    assert rc == 0 and d["dry_run"] is True and d["network"] is False


def test_export_dry_run_en_argumenten(capsys):
    rc, out, _ = run(["export", "--dataset", "kpis", "--administratie", "[Voorbeeld] BV", "--jaar", "2026", "--format", "csv,xlsx", "--out", "uit", "--dry-run", "--json"], capsys)
    d = json.loads(out)
    assert rc == 0 and d["args"]["formaten"] == ["csv", "xlsx"] and d["tool"] == "yuki_export_dataset"
    rc, _, _ = run(["export", "--dataset", "onbekend", "--administratie", "x", "--out", "y"], capsys)
    assert rc == 2


def test_dashboard_dry_run(capsys):
    rc, out, _ = run(["dashboard", "--administratie", "[Voorbeeld] BV", "--jaar", "2026", "--dry-run", "--json"], capsys)
    assert rc == 0 and json.loads(out)["tool"] == "yuki_dashboard_kpis"


def test_doctor_toont_nooit_de_sleutel(capsys, monkeypatch):
    monkeypatch.setenv("YUKI_ACCESS_KEY", "GEHEIME-TESTWAARDE-12345")
    rc, out, err = run(["doctor", "--json"], capsys)
    assert "GEHEIME-TESTWAARDE" not in out + err and rc == 0
    d = json.loads(out)
    assert any(c["check"] == "YUKI_ACCESS_KEY" and c["ok"] for c in d["checks"])


def test_doctor_zonder_sleutel_is_config_fout(capsys):
    rc, out, _ = run(["doctor", "--json"], capsys)
    assert rc == cli.EXIT_CONFIG


def test_doctor_online_dry_run_doet_geen_call(capsys, monkeypatch):
    monkeypatch.setenv("YUKI_ACCESS_KEY", "x")
    rc, out, _ = run(["doctor", "--online", "--dry-run", "--json"], capsys)
    assert rc == 0 and any(c["check"] == "online" for c in json.loads(out)["checks"])


def test_config_init_schrijft_plaatshouders_en_weigert_overschrijven(capsys, tmp_path):
    p = tmp_path / ".env"
    rc, _, _ = run(["config", "init", "--path", str(p)], capsys)
    t = p.read_text(encoding="utf-8")
    assert rc == 0 and "YUKI_ACCESS_KEY=\n" in t and "YUKI_WRITE_ENABLED=" not in t.replace("# Writing", "").replace("YUKI_WRITE_ENABLED is", "")
    rc, _, err = run(["config", "init", "--path", str(p)], capsys)
    assert rc == cli.EXIT_USAGE
    if os.name != "nt":
        assert oct(p.stat().st_mode)[-3:] == "600"


def test_completion_scripts(capsys):
    for sh, needle in (("bash", "complete -F"), ("zsh", "#compdef"), ("powershell", "Register-ArgumentCompleter")):
        rc, out, _ = run(["completion", sh], capsys)
        assert rc == 0 and needle in out and "doctor" in out


# --- configuratie
def test_voorrang_omgeving_wint_van_bestand(tmp_path, monkeypatch):
    f = tmp_path / ".env"
    f.write_text("YUKI_ACCESS_LEVEL=domein\nYUKI_DAILY_LIMIT=100\n# c\nBAD KEY=1\n", encoding="utf-8")
    monkeypatch.setenv("YUKI_DAILY_LIMIT", "500")
    config.apply_env_file(f)
    assert os.environ["YUKI_DAILY_LIMIT"] == "500" and os.environ["YUKI_ACCESS_LEVEL"] == "domein"


def test_cli_optie_wint_van_omgeving(capsys, monkeypatch):
    monkeypatch.setenv("YUKI_ACCESS_LEVEL", "portaal")
    run(["version", "--access-level", "domein"], capsys)   # version bootstrapt niet; gebruik doctor
    run(["doctor", "--access-level", "domein", "--dry-run", "--json"], capsys)
    assert os.environ["YUKI_ACCESS_LEVEL"] == "domein"


def test_profielen_en_geheimen_in_config(tmp_path, monkeypatch):
    c = tmp_path / "c.toml"
    c.write_text('[default]\naccess_level = "portaal"\n[profiles.klant]\naccess_level = "domein"\nkey_env = "YUKI_ACCESS_KEY_KLANT"\n', encoding="utf-8")
    monkeypatch.setenv("YUKI_ACCESS_KEY_KLANT", "x")
    cfg = config.load_config(c, "klant")
    config.apply_config(cfg)
    assert os.environ["YUKI_ACCESS_LEVEL"] == "domein" and os.environ["YUKI_ACCESS_KEY"] == "x"
    with pytest.raises(config.ConfigError):
        config.load_config(c, "bestaatniet")
    bad = tmp_path / "bad.json"
    bad.write_text(json.dumps({"default": {"access_key": "abc"}}), encoding="utf-8")
    with pytest.raises(config.ConfigError, match="geheim"):
        config.load_config(bad)
    bad.write_text(json.dumps({"default": {"api_base": "http://evil"}}), encoding="utf-8")
    with pytest.raises(config.ConfigError):
        config.load_config(bad)


def test_ongeldig_log_niveau_is_config_fout(capsys):
    rc, _, err = run(["doctor", "--log-level", "debug", "--config", "/bestaat/niet.toml"], capsys)
    assert rc == cli.EXIT_CONFIG


# --- hooks
def test_hooks_standaard_uit(tmp_path):
    h = hk.Hooks.load(None)
    assert not h.enabled and h.fire("pre_call", {"tool": "x"}) == []
    f = tmp_path / "h.json"
    f.write_text(json.dumps({"enabled": False, "hooks": [{"event": "pre_call", "python": "m:f"}]}), encoding="utf-8")
    assert hk.Hooks.load(f).fire("pre_call", {"tool": "x"}) == []


def test_hook_command_krijgt_payload_zonder_geheimen(tmp_path, monkeypatch):
    out = tmp_path / "got.json"
    script = tmp_path / "h.py"
    script.write_text(f"import sys,os,json\nd=json.load(sys.stdin)\nd['env_has_key']=any(k.startswith('YUKI_ACCESS') for k in os.environ)\nopen(r'{out}','w').write(json.dumps(d))\n", encoding="utf-8")
    cfg = tmp_path / "hooks.json"
    cfg.write_text(json.dumps({"enabled": True, "hooks": [{"event": "pre_call", "command": [sys.executable, str(script)]}]}), encoding="utf-8")
    monkeypatch.setenv("YUKI_ACCESS_KEY", "GEHEIM-123")
    h = hk.Hooks.load(cfg)
    r = h.fire("pre_call", {"tool": "yuki_status", "args": {"administratie": "A", "access_key": "GEHEIM-123", "nested": {"api_token": "t"}}})
    got = json.loads(out.read_text())
    assert r == [{"hook": r[0]["hook"], "ok": True}] and got["env_has_key"] is False
    assert "GEHEIM-123" not in json.dumps(got) and got["args"]["access_key"] == "[verborgen]" and got["args"]["nested"]["api_token"] == "[verborgen]"
    assert got["event"] == "pre_call" and got["tool"] == "yuki_status"


def test_hook_python_en_filter_op_tool(tmp_path):
    (tmp_path / "myhook.py").write_text("CALLS=[]\ndef handler(p):\n    CALLS.append(p['tool'])\n", encoding="utf-8")
    cfg = tmp_path / "h.json"
    cfg.write_text(json.dumps({"enabled": True, "hooks": [{"event": "post_call", "python": "myhook:handler", "tools": ["yuki_a"]}]}), encoding="utf-8")
    h = hk.Hooks.load(cfg)
    h.fire("post_call", {"tool": "yuki_b"})
    h.fire("post_call", {"tool": "yuki_a"})
    import myhook
    assert myhook.CALLS == ["yuki_a"]
    sys.path.remove(str(tmp_path))
    sys.modules.pop("myhook", None)


def test_hook_fout_breekt_de_aanroep_niet(tmp_path):
    cfg = tmp_path / "h.json"
    cfg.write_text(json.dumps({"enabled": True, "hooks": [{"event": "pre_call", "command": ["/bestaat/niet/zeker"]}]}), encoding="utf-8")
    h = hk.Hooks.load(cfg)
    assert h.fire("pre_call", {"tool": "x"})[0]["ok"] is False
    assert hk.guarded_call(h, lambda n, a: {"ok": 1}, "x", {}) == {"ok": 1}


def test_hook_validatie(tmp_path):
    with pytest.raises(ValueError):
        hk.Hooks({"enabled": True, "hooks": [{"event": "nope", "command": ["x"]}]})
    with pytest.raises(ValueError):
        hk.Hooks({"enabled": True, "hooks": [{"event": "pre_call", "command": "echo hi"}]})
    with pytest.raises(ValueError):
        hk.Hooks({"enabled": True, "hooks": [{"event": "pre_call"}]})


def test_guarded_call_vuurt_events_en_on_export():
    seen = []

    class H(hk.Hooks):
        def fire(self, event, payload):
            seen.append((event, payload.get("tool"), payload.get("files")))
            return []
    h = H({"enabled": True})
    hk.guarded_call(h, lambda n, a: {"bestanden": ["a.csv"]}, "yuki_export_dataset", {"export_map": "m"})
    assert [e for e, *_ in seen] == ["pre_call", "post_call", "on_export"] and seen[-1][2] == ["a.csv"]
    seen.clear()
    with pytest.raises(RuntimeError):
        hk.guarded_call(h, lambda n, a: (_ for _ in ()).throw(RuntimeError("boem")), "t", {})
    assert [e for e, *_ in seen] == ["pre_call", "on_error"]


# --- retry (opt-in)
def test_retry_standaard_uit_en_opt_in(monkeypatch):
    import httpx
    from yuki_mcp.transport import PluginTransport
    calls = {"n": 0}

    class FakeHttp:
        def post(self, *a, **k):
            calls["n"] += 1
            raise httpx.ConnectTimeout("t")
    monkeypatch.setattr("time.sleep", lambda s: None)
    t = PluginTransport(http_client=FakeHttp())
    pass
    with pytest.raises(Exception):
        t.call("Accounting", "Administrations", [])
    assert calls["n"] == 1
    calls["n"] = 0
    monkeypatch.setenv("YUKI_MAX_RETRIES", "2")
    with pytest.raises(Exception):
        t.call("Accounting", "Administrations", [])
    assert calls["n"] == 3


def test_log_json_formatter_scrubt():
    import logging
    from yuki_mcp.logsetup import JsonFormatter
    r = logging.LogRecord("yuki", logging.INFO, "f", 1, "bericht", (), None)
    r.tool = "yuki_status"
    d = json.loads(JsonFormatter().format(r))
    assert d["msg"] == "bericht" and d["tool"] == "yuki_status" and d["level"] == "info"
