#!/usr/bin/env python3
"""CLI-alternatief voor bots zonder MCP-registratie. Zelfde tools, zelfde limiet en teller als de MCP-server.

  run_cli.py list                       -> alle tools (naam, korte omschrijving)
  run_cli.py schema <tool>              -> JSON-schema van de argumenten
  run_cli.py <tool> '<json-argumenten>' -> voert de tool uit; JSON op stdout; exitcode 1 bij fout
Sleutel via omgeving (YUKI_ACCESS_KEY of alias YUKI_API_KEY); nooit als argument meegeven.
"""
import json
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
venv_py = ROOT / ".venv" / "bin" / "python"
if venv_py.exists() and Path(sys.executable).resolve() != venv_py.resolve() and not os.environ.get("YUKI_NO_VENV"):
    os.execv(str(venv_py), [str(venv_py), __file__, *sys.argv[1:]])
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "vendor"))
try:
    import httpx, cryptography  # noqa: F401,E401
except ImportError:
    sys.stderr.write("Ontbrekende afhankelijkheden. Installeer: python3 -m pip install -r requirements.txt\n")
    sys.exit(1)
from yuki_mcp.clientfactory import ClientFactory  # noqa: E402
from yuki_mcp.server import Server  # noqa: E402


def _rpc(srv, method, params=None):
    return srv.handle({"jsonrpc": "2.0", "id": 1, "method": method, "params": params or {}})["result"]


def main(argv, srv=None) -> int:
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(__doc__)
        return 0
    srv = srv or Server(ClientFactory())
    cmd = argv[0]
    if cmd == "list":
        for t in _rpc(srv, "tools/list")["tools"]:
            print(f"{t['name']}\t{(t.get('description') or '').splitlines()[0][:110]}")
        return 0
    if cmd == "schema":
        tools = {t["name"]: t for t in _rpc(srv, "tools/list")["tools"]}
        if len(argv) < 2 or argv[1] not in tools:
            sys.stderr.write("Onbekende tool. Gebruik: run_cli.py list\n")
            return 2
        print(json.dumps(tools[argv[1]]["inputSchema"], ensure_ascii=False, indent=2))
        return 0
    try:
        args = json.loads(argv[1]) if len(argv) > 1 else {}
        if not isinstance(args, dict):
            raise ValueError
    except ValueError:
        sys.stderr.write("Argumenten moeten één JSON-object zijn, bv. '{\"administratie\": \"...\"}'\n")
        return 2
    r = _rpc(srv, "tools/call", {"name": cmd, "arguments": args})
    sys.stdout.write(r["content"][0]["text"] + "\n")
    return 1 if r.get("isError") else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
