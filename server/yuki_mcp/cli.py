"""Opdrachtregel: serve, doctor, tools, call, export, dashboard, config init, version, completion. Alleen lezen.

Voorrang van instellingen: CLI-opties > omgeving > bestand (.env / config). Geheimen worden nooit afgedrukt.
Exitcodes: 0 ok, 1 algemene fout, 2 gebruik (argparse), 3 configuratie/omgeving, 4 tool- of Yuki-fout, 5 netwerk (doctor --online), 6 geweigerd (niet alleen-lezen).
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Optional

from . import __version__, edition
from .config import ENV_TEMPLATE, ConfigError, apply_config, apply_env_file, load_config
from .logsetup import setup as setup_logging

EXIT_OK, EXIT_ERR, EXIT_USAGE, EXIT_CONFIG, EXIT_TOOL, EXIT_NET, EXIT_REFUSED = 0, 1, 2, 3, 4, 5, 6
COMMANDS = ["serve", "doctor", "tools", "call", "export", "dashboard", "config", "workflows", "transfer", "version", "completion"]
PROG = "yuki-api-connector"


class Out:
    def __init__(self, as_json: bool, quiet: bool) -> None:
        self.as_json, self.quiet = as_json, quiet

    def emit(self, data: Any, text: Optional[str] = None) -> None:
        if self.as_json:
            sys.stdout.write(json.dumps(data, ensure_ascii=False, indent=2, default=str) + "\n")
        elif not self.quiet:
            sys.stdout.write((text if text is not None else json.dumps(data, ensure_ascii=False, indent=2, default=str)) + "\n")

    def info(self, text: str) -> None:
        if not self.quiet and not self.as_json:
            sys.stdout.write(text + "\n")


def _common() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(add_help=False)
    S = argparse.SUPPRESS
    p.add_argument("--json", action="store_true", default=S, help="machine-leesbare JSON-uitvoer")
    p.add_argument("-q", "--quiet", action="store_true", default=S, help="alleen fouten")
    p.add_argument("-v", "--verbose", action="store_true", default=S, help="meer details (debug-logging)")
    p.add_argument("--log-level", choices=["debug", "info", "warning", "error", "critical"], default=S)
    p.add_argument("--log-format", choices=["text", "json"], default=S, help="structurele JSON-logregels op stderr")
    p.add_argument("--env-file", default=S, help=".env-bestand (omgeving wint)")
    p.add_argument("--config", default=S, help="config.toml of .json met [default] en [profiles.NAAM] (geen geheimen)")
    p.add_argument("--profile", default=S, help="profiel uit het configbestand")
    p.add_argument("--hooks", default=S, help="hooks-bestand (standaard uit, zie docs/HOOKS.md)")
    p.add_argument("--dry-run", action="store_true", default=S, help="toon wat er zou gebeuren; geen Yuki-calls")
    p.add_argument("--access-level", choices=["portaal", "domein"], default=S, help="overschrijft YUKI_ACCESS_LEVEL")
    p.add_argument("--data-dir", default=S, help="overschrijft YUKI_DATA_DIR")
    return p


def build_parser() -> argparse.ArgumentParser:
    c = _common()
    ap = argparse.ArgumentParser(prog=PROG, parents=[c], description=f"{edition.DISPLAY_NAME}: alleen-lezen Yuki-koppeling (MCP-server en opdrachtregel).",
                                 epilog="Voor Belgische boekhouders/accountants (MAR, Belgisch btw-stelsel). Buiten België: verifieer zelf de lokale regels.")
    sub = ap.add_subparsers(dest="cmd", metavar="opdracht")
    s = sub.add_parser("serve", parents=[c], help="start de MCP-server (stdio)")
    s.add_argument("--http", action="store_true", help="optioneel lokaal HTTP-eindpunt (alleen 127.0.0.1/localhost, minimaal JSON-RPC, geen SSE)")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8765)
    d = sub.add_parser("doctor", parents=[c], help="controleer Python, afhankelijkheden en omgeving (zonder geheimen)")
    d.add_argument("--online", action="store_true", help="test ook de verbinding met Yuki (1 call)")
    t = sub.add_parser("tools", parents=[c], help="lijst van de tools")
    t.add_argument("--names-only", action="store_true")
    ca = sub.add_parser("call", parents=[c], help="roep één (alleen-lezen) tool aan")
    ca.add_argument("tool")
    ca.add_argument("--args", default="{}", help="JSON-object of @bestand.json")
    e = sub.add_parser("export", parents=[c], help="exporteer een dataset (csv, json, xlsx, parquet)")
    e.add_argument("--dataset", required=True, choices=["kpis", "saldi", "openstaande_posten"])
    e.add_argument("--administratie", required=True)
    e.add_argument("--jaar", type=int)
    e.add_argument("--periode", help="jaar, kwartaal:n of maand:n")
    e.add_argument("--peildatum", help="JJJJ-MM-DD")
    e.add_argument("--soort", choices=["debiteuren", "crediteuren"])
    e.add_argument("--format", default="csv,json", help="komma-gescheiden: csv,json,xlsx,parquet")
    e.add_argument("--out", required=True, help="doelmap")
    b = sub.add_parser("dashboard", parents=[c], help="kerncijfers in de terminal of als JSON-bestand")
    b.add_argument("--administratie", required=True)
    b.add_argument("--jaar", type=int, required=True)
    b.add_argument("--periode")
    b.add_argument("--vergelijk", action="store_true", help="vergelijk met de vorige periode")
    b.add_argument("--out", help="schrijf JSON naar dit bestand")
    cf = sub.add_parser("config", parents=[c], help="configuratie")
    cs = cf.add_subparsers(dest="config_cmd", metavar="actie")
    ci = cs.add_parser("init", parents=[c], help="schrijf een voorbeeld-.env met plaatshouders")
    ci.add_argument("--path", default=".env")
    ci.add_argument("--force", action="store_true")
    wf = sub.add_parser("workflows", parents=[c], help="automatisering: vergaderingvoorbereiding en terugkerende verplichtingen (alleen lezen, concepten)")
    ws = wf.add_subparsers(dest="wf_cmd", metavar="actie")
    wc = argparse.ArgumentParser(add_help=False)
    wc.add_argument("-w", "--workflows-file", default=os.environ.get("YUKI_WORKFLOWS_FILE", "workflows.toml"), help="workflows-config (TOML/JSON, geen geheimen)")
    wc.add_argument("--days", type=int, help="vergaderingen binnen N dagen (standaard uit config, 2)")
    wc.add_argument("--today", help="JJJJ-MM-DD (voor tests en herhalingen)")
    wc.add_argument("--only", choices=["meetings", "obligations"])
    ws.add_parser("plan", parents=[c, wc], help="toon wat voorbereid moet worden (geen Yuki-calls)")
    ws.add_parser("list", parents=[c, wc], help="toon klanten en verplichtingen uit de config")
    wr = ws.add_parser("run", parents=[c, wc], help="maak overzichten en conceptmails (verstuurt niets standaard)")
    wr.add_argument("--out", help="uitvoermap (standaard settings.out_dir)")
    wr.add_argument("--force", action="store_true", help="ook items die al gedaan zijn opnieuw maken")
    wr.add_argument("--send", action="store_true", help="vraag om te versturen (SMTP; vereist allow_send in de config)")
    wr.add_argument("--confirm-send", action="store_true", help="bevestiging per run voor --send (anders typt u VERSTUUR in een terminal)")
    wi = ws.add_parser("init", parents=[c], help="schrijf een voorbeeld-workflows.toml")
    wi.add_argument("--path", default="workflows.toml")
    wi.add_argument("--force", action="store_true")
    tr = sub.add_parser("transfer", parents=[c], help="dossieroverdracht per boekjaar voor de volgende boekhouder (alleen lezen voor Yuki)")
    ts = tr.add_subparsers(dest="transfer_cmd", metavar="actie")
    te = ts.add_parser("export", parents=[c], help="exporteer per boekjaar (met schatting, bevestiging, checkpoint, MANIFEST en CONTROL)")
    te.add_argument("--administration", "--administratie", dest="administratie", required=True)
    te.add_argument("--fiscal-year", "--boekjaar", dest="fiscal_year", type=int, action="append", help="boekjaar (jaartal); herhaalbaar")
    te.add_argument("--all-years", action="store_true", help="alle jaren vanaf --first-year (standaard huidig jaar min 5)")
    te.add_argument("--first-year", type=int)
    te.add_argument("--out", required=True, help="doelmap")
    te.add_argument("--zip", action="store_true", help="ook een zip per jaar")
    te.add_argument("--include-documents", action="store_true", help="ook documentmetadata uit het archief (geen bestandsinhoud)")
    te.add_argument("--all-accounts", action="store_true", help="mutaties van elke rekening (meer calls)")
    te.add_argument("--fy-start-month", type=int, default=1, help="eerste maand van het boekjaar (standaard 1)")
    te.add_argument("--format", default="csv,json", help="csv,json,xlsx")
    te.add_argument("--threshold", type=int, default=150, help="vraag bevestiging boven dit aantal calls")
    te.add_argument("--yes", action="store_true", help="bevestig na de schatting (voor niet-interactief gebruik)")
    te.add_argument("--estimate-only", action="store_true", help="toon alleen de schatting")
    te.add_argument("--no-resume", action="store_true", help="negeer het checkpoint")
    te.add_argument("--domain", dest="domain")
    sub.add_parser("version", parents=[c], help="toon de versie")
    co = sub.add_parser("completion", parents=[c], help="shell-aanvulling (bash, zsh, powershell)")
    co.add_argument("shell", choices=["bash", "zsh", "powershell"])
    return ap


def completion_script(shell: str) -> str:
    words = " ".join(COMMANDS)
    opts = "--json --quiet --verbose --log-level --log-format --env-file --config --profile --hooks --dry-run --access-level --data-dir --help"
    if shell == "bash":
        return f'_yuki_api_connector() {{\n  local cur="${{COMP_WORDS[COMP_CWORD]}}"\n  if [ "$COMP_CWORD" -eq 1 ]; then COMPREPLY=( $(compgen -W "{words}" -- "$cur") )\n  else COMPREPLY=( $(compgen -W "{opts}" -- "$cur") ); fi\n}}\ncomplete -F _yuki_api_connector {PROG}\n'
    if shell == "zsh":
        return f"#compdef {PROG}\n_arguments '1:command:({words})' '*:option:({opts})'\n"
    return (f"Register-ArgumentCompleter -Native -CommandName {PROG} -ScriptBlock {{\n  param($wordToComplete)\n  '{words}'.Split(' ') + '{opts}'.Split(' ') |\n"
            "    Where-Object { $_ -like \"$wordToComplete*\" } | ForEach-Object { [System.Management.Automation.CompletionResult]::new($_, $_, 'ParameterValue', $_) }\n}\n")


def _bootstrap(a: argparse.Namespace) -> None:
    """Instellingen laden in volgorde: CLI (hier eerst) > omgeving (bestaat al) > bestanden (setdefault)."""
    if getattr(a, "access_level", None):
        os.environ["YUKI_ACCESS_LEVEL"] = a.access_level
    if getattr(a, "data_dir", None):
        os.environ["YUKI_DATA_DIR"] = a.data_dir
    if getattr(a, "hooks", None):
        os.environ["YUKI_HOOKS_FILE"] = a.hooks
    cfgp = getattr(a, "config", None)
    if cfgp:
        apply_config(load_config(Path(cfgp), getattr(a, "profile", None)))
    elif getattr(a, "profile", None):
        raise ConfigError("--profile vraagt ook --config.")
    envf = getattr(a, "env_file", None)
    if envf:
        apply_env_file(Path(envf))
    setup_logging(getattr(a, "log_level", None), getattr(a, "log_format", None), getattr(a, "quiet", False), getattr(a, "verbose", False))


def _tools():
    from .clientfactory import ClientFactory
    from .tools import Tools
    return Tools(ClientFactory())


def _read_only(tools, name: str) -> Optional[str]:
    d = tools.defs.get(name)
    if d is None:
        return f"Onbekende tool: {name}. Zie '{PROG} tools'."
    if not d.get("annotations", {}).get("readOnlyHint", False) or name.startswith("yuki_boeking_"):
        return f"{name} is niet alleen-lezen en wordt via de opdrachtregel niet uitgevoerd."
    return None


def _validate(schema: dict, args: dict) -> list[str]:
    miss = [r for r in schema.get("required", []) if r not in args]
    unknown = [k for k in args if schema.get("properties") and k not in schema["properties"]]
    return ([f"ontbrekende parameter: {m}" for m in miss] + [f"onbekende parameter: {u}" for u in unknown])


def _run_tool(a, out: Out, name: str, args: dict) -> int:
    from .hooks import Hooks, guarded_call
    tools = _tools()
    bad = _read_only(tools, name)
    if bad:
        sys.stderr.write(bad + "\n")
        return EXIT_REFUSED if name in tools.defs else EXIT_USAGE
    problems = _validate(tools.defs[name]["inputSchema"], args)
    if problems:
        sys.stderr.write("; ".join(problems) + "\n")
        return EXIT_USAGE
    if getattr(a, "dry_run", False):
        out.emit({"dry_run": True, "tool": name, "args": args, "network": False}, f"[dry-run] zou {name} aanroepen met {json.dumps(args, ensure_ascii=False)}; geen Yuki-calls gedaan.")
        return EXIT_OK
    try:
        res = guarded_call(Hooks.from_env(), tools.call, name, args)
    except Exception as exc:  # noqa: BLE001
        from .convert import scrub
        sys.stderr.write(scrub(f"{type(exc).__name__}: {exc}") + "\n")
        code = EXIT_CONFIG if type(exc).__name__ == "YukiConfigError" else EXIT_TOOL
        return code
    out.emit(res)
    return EXIT_OK


def cmd_doctor(a, out: Out) -> int:
    checks: list[dict] = []

    def add(name: str, ok: bool, detail: str, level: str = "error") -> None:
        checks.append({"check": name, "ok": ok, "level": "ok" if ok else level, "detail": detail})
    add("python", sys.version_info >= (3, 10), f"Python {sys.version.split()[0]} (nodig: 3.10+)")
    for mod in ("httpx", "cryptography"):
        try:
            __import__(mod)
            add(mod, True, "geïnstalleerd")
        except ImportError:
            add(mod, False, "ontbreekt: pip install -r requirements.txt")
    try:
        __import__("pyarrow")
        add("pyarrow (optioneel)", True, "geïnstalleerd (Parquet beschikbaar)")
    except ImportError:
        add("pyarrow (optioneel)", True, "niet geïnstalleerd; alleen nodig voor Parquet", "info")
    key = bool(os.environ.get("YUKI_ACCESS_KEY") or os.environ.get("YUKI_API_KEY"))
    add("YUKI_ACCESS_KEY", key, "ingesteld (waarde wordt nooit getoond)" if key else "niet ingesteld")
    lvl = os.environ.get("YUKI_ACCESS_LEVEL", "portaal").lower()
    add("YUKI_ACCESS_LEVEL", lvl in ("portaal", "portal", "domein", "domain"), f"'{lvl}'" if lvl in ("portaal", "portal", "domein", "domain") else "ongeldig: portaal of domein")
    wr = os.environ.get("YUKI_WRITE_ENABLED", "").strip().lower() in ("ja", "true", "1", "yes")
    add("schrijven (YUKI_WRITE_ENABLED)", not wr, "UIT (standaard, aanbevolen)" if not wr else "AAN: boekingsworkflow actief; zet uit tenzij bewust", "warning")
    hf = os.environ.get("YUKI_HOOKS_FILE")
    if hf:
        try:
            from .hooks import Hooks
            h = Hooks.load(hf)
            add("hooks", True, f"{'aan' if h.enabled else 'uit (enabled=false)'}, {len(h.hooks)} actief")
        except Exception as exc:  # noqa: BLE001
            add("hooks", False, f"ongeldig bestand: {type(exc).__name__}")
    else:
        add("hooks", True, "uit (geen YUKI_HOOKS_FILE)", "info")
    try:
        from yuki_core.paths import default_data_dir  # type: ignore
    except ImportError:
        from yuki_core.paths import default_data_dir  # type: ignore
    try:
        d = Path(default_data_dir())
        d.mkdir(parents=True, exist_ok=True)
        add("datamap", os.access(d, os.W_OK), f"{d}")
    except Exception as exc:  # noqa: BLE001
        add("datamap", False, type(exc).__name__)
    rc = EXIT_OK
    if any(not c["ok"] and c["level"] == "error" for c in checks):
        rc = EXIT_CONFIG
    if getattr(a, "online", False) and rc == EXIT_OK:
        if getattr(a, "dry_run", False):
            add("online", True, "[dry-run] overgeslagen", "info")
        else:
            try:
                _tools().call("yuki_administraties", {})
                add("online", True, "verbinding met Yuki werkt (1 call)")
            except Exception as exc:  # noqa: BLE001
                add("online", False, f"mislukt: {type(exc).__name__}")
                rc = EXIT_NET
    out.emit({"ok": rc == EXIT_OK, "checks": checks}, "\n".join(f"[{c['level'].upper():7}] {c['check']}: {c['detail']}" for c in checks))
    return rc


def _cmd_transfer(a, out: Out) -> int:
    """Schatting eerst; boven de drempel of boven het resterende daglimiet vraagt dit bevestiging (--yes of 'JA' in een terminal)."""
    from .hooks import Hooks, guarded_call
    if getattr(a, "transfer_cmd", None) != "export":
        sys.stderr.write(f"Gebruik: {PROG} transfer export --administration X --fiscal-year YYYY --out MAP\n")
        return EXIT_USAGE
    if not a.fiscal_year and not a.all_years:
        sys.stderr.write("Geef --fiscal-year JJJJ (herhaalbaar) of --all-years. De Yuki-API levert geen lijst van boekjaren.\n")
        return EXIT_USAGE
    fmts = [f.strip() for f in a.format.split(",") if f.strip()]
    args: dict = {"administratie": a.administratie, "export_map": str(Path(a.out).expanduser()), "zip": a.zip, "inclusief_documenten": a.include_documents,
                  "alle_rekeningen": a.all_accounts, "start_maand_boekjaar": a.fy_start_month, "formaten": fmts, "drempel": a.threshold, "hervat": not a.no_resume}
    if a.domain:
        args["domein"] = a.domain
    if a.all_years:
        args["alle_jaren"] = True
        if a.first_year:
            args["eerste_jaar"] = a.first_year
    else:
        args["jaren"] = a.fiscal_year
    tools = _tools()
    hooks = Hooks.from_env()
    if getattr(a, "dry_run", False):
        out.emit({"dry_run": True, "tool": "yuki_dossier_transfer_export", "args": args, "network": False}, "[dry-run] zou de dossieroverdracht uitvoeren met " + json.dumps(args, ensure_ascii=False) + "; geen Yuki-calls gedaan.")
        return EXIT_OK
    try:
        est = guarded_call(hooks, tools.call, "yuki_dossier_transfer_export", {**args, "alleen_schatting": True})
        e = est["estimate"]
        out.info(f"Schatting: hoogstens {e['max_calls']} calls voor {e['years']} boekjaar/boekjaren (resterend vandaag: {e['remaining_today']}). {e['note']}")
        if a.estimate_only:
            out.emit(est)
            return EXIT_OK
        need = e["max_calls"] > a.threshold or e["exceeds_remaining"]
        if need and not a.yes:
            if sys.stdin.isatty():
                if input("Doorgaan? Typ JA om te bevestigen: ").strip() != "JA":
                    sys.stderr.write("Niet bevestigd; niets geëxporteerd.\n")
                    return EXIT_REFUSED
            else:
                sys.stderr.write("Bevestiging nodig boven de drempel: herhaal met --yes (of verhoog --threshold).\n")
                return EXIT_REFUSED
        res = guarded_call(hooks, tools.call, "yuki_dossier_transfer_export", {**args, "bevestig": True})
    except Exception as exc:  # noqa: BLE001
        from .convert import scrub
        sys.stderr.write(scrub(f"{type(exc).__name__}: {exc}") + "\n")
        return EXIT_CONFIG if type(exc).__name__ == "YukiConfigError" else EXIT_TOOL
    out.emit(res, f"Status: {res['status']}. Uitvoer: {res['out']}" + (f". {res['interrupted']}" if res.get("interrupted") else ""))
    if hooks.enabled and res.get("status") == "klaar":
        hooks.fire("on_export", {"tool": "yuki_dossier_transfer_export", "files": [str(Path(res["out"]) / "README.md")], "export_dir": res["out"]})
    return EXIT_OK if res["status"] == "klaar" else EXIT_TOOL


def cmd_serve(a, out: Out) -> int:
    from . import server
    if getattr(a, "http", False):
        return _serve_http(a.host, a.port)
    return server.main()


def _serve_http(host: str, port: int) -> int:
    from http.server import BaseHTTPRequestHandler, HTTPServer
    from .server import Server
    if host not in ("127.0.0.1", "localhost", "::1"):
        sys.stderr.write("--http luistert alleen op localhost (127.0.0.1).\n")
        return EXIT_REFUSED
    srv = Server()
    allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}", f"[::1]:{port}"}

    class H(BaseHTTPRequestHandler):
        def log_message(self, *args):  # geen toegangslog met inhoud
            return

        def do_POST(self):  # noqa: N802
            origin = self.headers.get("Origin")
            if self.headers.get("Host", "") not in allowed_hosts or (origin and not origin.startswith(("http://127.0.0.1", "http://localhost"))):
                self.send_error(403)
                return
            try:
                n = int(self.headers.get("Content-Length", "0"))
                msg = json.loads(self.rfile.read(min(n, 5_000_000)))
            except (ValueError, json.JSONDecodeError):
                self.send_error(400)
                return
            resp = srv.handle(msg)
            body = json.dumps(resp, ensure_ascii=False).encode("utf-8") if resp is not None else b""
            self.send_response(200 if resp is not None else 202)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
    httpd = HTTPServer((host, port), H)
    sys.stderr.write(f"HTTP-eindpunt op http://{host}:{port}/ (alleen lokaal; geen authenticatie). Stop met Ctrl+C.\n")
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    return EXIT_OK


def cmd_config_init(a, out: Out) -> int:
    p = Path(a.path)
    if p.exists() and not a.force:
        sys.stderr.write(f"{p} bestaat al; gebruik --force om te overschrijven.\n")
        return EXIT_USAGE
    fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8", newline="\n") as fh:
        fh.write(ENV_TEMPLATE)
    out.emit({"written": str(p)}, f"Voorbeeldbestand geschreven: {p} (alleen plaatshouders; commit het nooit).")
    return EXIT_OK


def main(argv: Optional[list[str]] = None) -> int:
    from .config import drop_unresolved_placeholders
    drop_unresolved_placeholders()
    ap = build_parser()
    try:
        a = ap.parse_args(argv)
    except SystemExit as e:  # argparse: 2 bij gebruiksfout, 0 bij --help
        return int(e.code or 0)
    if not a.cmd:
        ap.print_help()
        return EXIT_USAGE
    out = Out(getattr(a, "json", False), getattr(a, "quiet", False))
    if a.cmd == "version":
        out.emit({"name": edition.PLUGIN_NAME, "version": __version__, "edition": edition.EDITION}, f"{edition.DISPLAY_NAME} {__version__}")
        return EXIT_OK
    if a.cmd == "completion":
        sys.stdout.write(completion_script(a.shell))
        return EXIT_OK
    try:
        _bootstrap(a)
    except (ConfigError, ValueError, OSError) as exc:
        sys.stderr.write(f"Configuratiefout: {exc}\n")
        return EXIT_CONFIG
    try:
        if a.cmd == "serve":
            return cmd_serve(a, out)
        if a.cmd == "doctor":
            return cmd_doctor(a, out)
        if a.cmd == "tools":
            tl = _tools().list()
            names = [t["name"] for t in tl]
            if a.names_only:
                out.emit(names, "\n".join(names))
            else:
                out.emit([{"name": t["name"], "description": t["description"], "readOnly": t["annotations"].get("readOnlyHint", False)} for t in tl],
                         "\n".join(f"{t['name']}: {t['description'][:110]}" for t in tl))
            return EXIT_OK
        if a.cmd == "call":
            raw = a.args
            if raw.startswith("@"):
                raw = Path(raw[1:]).read_text(encoding="utf-8")
            try:
                args = json.loads(raw)
                if not isinstance(args, dict):
                    raise ValueError
            except ValueError:
                sys.stderr.write("--args moet een JSON-object zijn.\n")
                return EXIT_USAGE
            return _run_tool(a, out, a.tool, args)
        if a.cmd == "export":
            args = {"dataset": a.dataset, "administratie": a.administratie, "formaten": [f.strip() for f in a.format.split(",") if f.strip()],
                    "export_map": str(Path(a.out).expanduser())}
            for k in ("jaar", "periode", "peildatum", "soort"):
                if getattr(a, k, None) is not None:
                    args[k] = getattr(a, k)
            return _run_tool(a, out, "yuki_export_dataset", args)
        if a.cmd == "dashboard":
            args = {"administratie": a.administratie, "jaar": a.jaar, "vergelijk_vorige_periode": bool(a.vergelijk)}
            if a.periode:
                args["periode"] = a.periode
            if a.out and not getattr(a, "dry_run", False):
                # naar bestand: tool uitvoeren en JSON schrijven, niets op stdout behalve de bevestiging
                from .hooks import Hooks, guarded_call
                res = guarded_call(Hooks.from_env(), _tools().call, "yuki_dashboard_kpis", args)
                Path(a.out).expanduser().write_text(json.dumps(res, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
                out.emit({"written": a.out}, f"Kerncijfers geschreven naar {a.out}")
                return EXIT_OK
            return _run_tool(a, out, "yuki_dashboard_kpis", args)
        if a.cmd == "transfer":
            return _cmd_transfer(a, out)
        if a.cmd == "workflows":
            from .workflows import cmd_workflows
            return cmd_workflows(a, out)
        if a.cmd == "config":
            if getattr(a, "config_cmd", None) == "init":
                return cmd_config_init(a, out)
            sys.stderr.write(f"Gebruik: {PROG} config init\n")
            return EXIT_USAGE
    except KeyboardInterrupt:
        return 130
    except Exception as exc:  # noqa: BLE001
        from .convert import scrub
        sys.stderr.write(scrub(f"{type(exc).__name__}: {exc}") + "\n")
        return EXIT_CONFIG if type(exc).__name__ == "YukiConfigError" else EXIT_TOOL
    return EXIT_ERR


if __name__ == "__main__":
    sys.exit(main())
