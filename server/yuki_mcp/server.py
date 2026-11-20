"""Minimale MCP-server over stdio (JSON-RPC 2.0, één bericht per regel). Alleen lezen."""
from __future__ import annotations

import json
import sys
from typing import Any, Optional

from . import __version__, edition
from .attribution import AttributionError, verify_startup
from .clientfactory import ClientFactory
from .hooks import Hooks, guarded_call
from .render import MCP_APP_MIME, dashboard_html, widget_resource
from .tools import UI_URI, Tools

PROTOCOL = "2025-06-18"


class Server:
    def __init__(self, factory: Optional[ClientFactory] = None) -> None:
        verify_startup(edition.REQUIRE_ATTRIBUTION)
        self.factory = factory or ClientFactory()
        self.tools = Tools(self.factory)
        self.hooks = Hooks.from_env()          # standaard UIT (YUKI_HOOKS_FILE)

    def handle(self, msg: dict) -> Optional[dict]:
        mid, method, params = msg.get("id"), msg.get("method"), msg.get("params") or {}
        if method is None:
            return None
        if mid is None:                      # notificatie
            return None
        try:
            result = self._dispatch(method, params)
        except KeyError as exc:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32601, "message": f"Onbekende methode: {exc.args[0]}"}}
        except AttributionError as exc:
            return {"jsonrpc": "2.0", "id": mid, "error": {"code": -32000, "message": str(exc)}}
        return {"jsonrpc": "2.0", "id": mid, "result": result}

    def _dispatch(self, method: str, p: dict) -> Any:
        if method == "initialize":
            return {"protocolVersion": PROTOCOL, "capabilities": {"tools": {"listChanged": False}, "resources": {}},
                    "serverInfo": {"name": edition.PLUGIN_NAME, "title": edition.DISPLAY_NAME, "version": __version__}}
        if method == "ping":
            return {}
        if method == "tools/list":
            return {"tools": self.tools.list()}
        if method == "tools/call":
            return self._call(p.get("name", ""), p.get("arguments"))
        if method == "resources/list":
            return {"resources": [widget_resource()]}
        if method == "resources/read":
            if p.get("uri") != UI_URI:
                raise KeyError(p.get("uri"))
            r = widget_resource()
            return {"contents": [{"uri": UI_URI, "mimeType": MCP_APP_MIME, "text": dashboard_html(None), "_meta": r["_meta"]}]}
        raise KeyError(method)

    def _call(self, name: str, args: Optional[dict]) -> dict:
        from .convert import scrub
        try:
            out = guarded_call(self.hooks, self.tools.call, name, args)
            text = json.dumps(out, ensure_ascii=False, default=str)
            res: dict = {"content": [{"type": "text", "text": text}], "isError": False}
            if isinstance(out, dict):
                res["structuredContent"] = out
            return res
        except AttributionError:
            raise
        except Exception as exc:  # noqa: BLE001 - fouten gaan als toolfout terug, zonder geheimen
            msg = scrub(f"{type(exc).__name__}: {exc}")
            return {"content": [{"type": "text", "text": msg}], "isError": True}


def main() -> int:
    from .config import drop_unresolved_placeholders
    drop_unresolved_placeholders()
    try:
        srv = Server()
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write(f"Start mislukt: {exc}\n")
        return 1
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            msg = json.loads(line)
        except json.JSONDecodeError:
            continue
        resp = srv.handle(msg)
        if resp is not None:
            sys.stdout.write(json.dumps(resp, ensure_ascii=False) + "\n")
            sys.stdout.flush()
    return 0
