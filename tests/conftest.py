"""Mock van de Yuki SOAP-laag: geen echte calls, geen echte sleutels."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

import httpx
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "server" / "vendor"))

FIXTURES = Path(__file__).parent / "fixtures"
NS = "http://www.theyukicompany.com/"
FAKE_KEY = "test-access-key-not-real"
FAKE_CACHE = "test-cache-secret-not-real"
ADMIN_1 = "00000000-0000-0000-0000-000000000001"


def envelope(method: str, inner: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/">'
            f'<soap:Body><{method}Response xmlns="{NS}"><{method}Result>{inner}</{method}Result></{method}Response>'
            '</soap:Body></soap:Envelope>')


def fault(msg: str) -> str:
    return ('<?xml version="1.0" encoding="utf-8"?><soap:Envelope xmlns:soap="http://schemas.xmlsoap.org/soap/envelope/"><soap:Body>'
            f'<soap:Fault><faultcode>soap:Server</faultcode><faultstring>{msg}</faultstring></soap:Fault></soap:Body></soap:Envelope>')


def docs(ids):
    return "<ArrayOfDocument>" + "".join(f"<Document><ID>d{i}</ID><Subject>Doc {i}</Subject></Document>" for i in ids) + "</ArrayOfDocument>"


def contacts(ids):
    return "<Contacts>" + "".join(f"<Contact><ID>c{i}</ID><Name>[Contact {i}]</Name></Contact>" for i in ids) + "</Contacts>"


class FakeYuki:
    def __init__(self) -> None:
        self.requests: list[tuple[str, str, str]] = []
        self.responses: dict[str, str] = {}
        self.sid = 0
        self.valid: set[str] = set()

    def methods(self):
        return [m for _, m, _ in self.requests]

    def handler(self, request: httpx.Request) -> httpx.Response:
        service = request.url.path.rsplit("/", 1)[-1].removesuffix(".asmx")
        method = request.headers["SOAPAction"].strip('"')[len(NS):]
        body = request.content.decode()
        self.requests.append((service, method, body))
        if method == "Authenticate":
            self.sid += 1
            s = f"fake-session-{self.sid}"
            self.valid.add(s)
            return httpx.Response(200, text=envelope("Authenticate", s))
        m = re.search(r"<sessionID>(.*?)</sessionID>", body)
        if not m or m.group(1) not in self.valid:
            return httpx.Response(500, text=fault("Invalid session ID. Please authenticate again."))
        if method in self.responses:
            r = self.responses[method]
            return httpx.Response(200, text=r if r.startswith("<?xml") else envelope(method, r))
        if method in ("Documents", "SearchContacts"):
            sr = re.search(r"<startRecord>(\d+)</startRecord>", body)
            pn = re.search(r"<pageNumber>(\d+)</pageNumber>", body)
            if method == "Documents":
                start = int(sr.group(1)) if sr else 0
                return httpx.Response(200, text=envelope(method, docs([1, 2, 3][start:start + 2])))
            page = int(pn.group(1)) if pn else 1
            return httpx.Response(200, text=envelope(method, contacts({1: [1, 2], 2: [3]}.get(page, []))))
        if method == "SetCurrentDomain":
            return httpx.Response(200, text=envelope(method, ""))
        if method == "GetCurrentDomain":
            return httpx.Response(200, text=envelope(method, "00000000-0000-0000-0000-000000000010"))
        fx = FIXTURES / f"{method}.xml"
        if fx.exists():
            return httpx.Response(200, text=envelope(method, fx.read_text()))
        return httpx.Response(500, text=fault(f"Unexpected method {method}"))


@pytest.fixture(autouse=True)
def _env(tmp_path, monkeypatch):
    monkeypatch.setenv("YUKI_DATA_DIR", str(tmp_path / "secrets"))
    monkeypatch.setenv("YUKI_RESPONSE_CACHE_DIR", str(tmp_path / "cache"))
    monkeypatch.setenv("YUKI_ACCESS_KEY", FAKE_KEY)
    monkeypatch.setenv("YUKI_CACHE_KEY", FAKE_CACHE)
    for v in ("YUKI_DAILY_LIMIT", "YUKI_DAILY_WARN", "YUKI_DAILY_LIMIT_APPROVAL", "YUKI_ACCESS_LEVEL", "YUKI_DOMAIN",
              "YUKI_RESPONSE_CACHE", "YUKI_CREDITOR_SIGN", "YUKI_BRAND_NAME", "YUKI_BRAND_COLOR", "YUKI_BRAND_LOGO_PATH",
              "YUKI_MAIL_SIGNATURE", "YUKI_LOG_RAW_DIR", "YUKI_API_KEY", "YUKI_WRITE_ENABLED", "YUKI_WRITE_TOKEN_TTL_MIN", "YUKI_WRITE_MAX_PER_DAY"):
        monkeypatch.delenv(v, raising=False)


@pytest.fixture
def fake():
    return FakeYuki()


@pytest.fixture
def server(fake):
    from yuki_mcp.clientfactory import ClientFactory
    from yuki_mcp.server import Server
    from yuki_mcp.transport import PluginTransport

    def make(**_):
        return Server(ClientFactory(transport_factory=lambda: PluginTransport(
            "https://api.example.test/ws", http_client=httpx.Client(transport=httpx.MockTransport(fake.handler)))))
    return make


class Rpc:
    def __init__(self, srv):
        self.srv, self.n = srv, 0

    def req(self, method, params=None):
        self.n += 1
        r = self.srv.handle({"jsonrpc": "2.0", "id": self.n, "method": method, "params": params or {}})
        return r

    def call(self, name, **args):
        r = self.req("tools/call", {"name": name, "arguments": args})["result"]
        return r


@pytest.fixture
def rpc(server):
    return Rpc(server())


@pytest.fixture(autouse=True)
def _geen_netwerk(monkeypatch):
    """Tests zijn deterministisch en offline: elke echte socketverbinding faalt."""
    import socket

    def _blocked(*a, **k):
        raise RuntimeError("Netwerktoegang is geblokkeerd in tests")
    monkeypatch.setattr(socket.socket, "connect", _blocked)
