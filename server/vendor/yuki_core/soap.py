"""Minimale SOAP 1.1-laag voor de Yuki-webservices.

- Namespace: http://www.theyukicompany.com/
- SOAPAction: "http://www.theyukicompany.com/<Methode>"
- Content-Type: text/xml; charset=utf-8
- Alleen TLS 1.2+ (httpx/ssl-context met minimum_version).
"""

from __future__ import annotations

import logging
import os
import re
import ssl
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable, Optional, Sequence, Tuple
from xml.etree import ElementTree as ET
from xml.sax.saxutils import escape

import httpx

from .errors import YukiError, YukiSoapFault

log = logging.getLogger("yuki_core.soap")

YUKI_NS = "http://www.theyukicompany.com/"
SOAP_ENV_NS = "http://schemas.xmlsoap.org/soap/envelope/"
DEFAULT_API_BASE = "https://api.yukiworks.be/ws"

# Alleen leesmethodes mogen via deze laag. Elke andere naam wordt geweigerd,
# zodat er nooit per ongeluk een schrijfactie vertrekt.
READ_ONLY_METHODS: dict[str, frozenset[str]] = {
    "Accounting": frozenset({
        "Authenticate", "Administrations", "AdministrationsWithInternalCustomerCode",
        "AdministrationID", "Domains", "GetCurrentDomain",
        "GLAccountBalance", "GLAccountBalanceFiscal", "GLAccountBalanceYearEnd",
        "GLAccountTransactions", "GLAccountTransactionsFiscal",
        "NetRevenue", "NetRevenueFiscal",
        "OutstandingDebtorItems", "OutstandingDebtorItemsByDateOutstanding",
        "OutstandingCreditorItems", "OutstandingCreditorItemsByDateOutstanding",
    }),
    "AccountingInfo": frozenset({
        "Authenticate", "Administrations", "AdministrationsWithInternalCustomerCode",
        "GetGLAccountScheme", "GetPeriodDateTable", "GetFinancialYearModifiedDate",
        "GetStartBalanceByGlAccount", "GetTransactionDetails", "GetTransactions",
    }),
}

Param = Tuple[str, Any]


def format_value(value: Any) -> str:
    """Zet een Python-waarde om naar een xs:-compatibele string."""
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.replace(tzinfo=None, microsecond=0).isoformat()
    if isinstance(value, date):
        return f"{value.isoformat()}T00:00:00"
    if isinstance(value, Decimal):
        return format(value, "f")
    return str(value)


def build_envelope(method: str, params: Sequence[Param]) -> str:
    """Bouw een SOAP 1.1-envelope. Volgorde van ``params`` = volgorde in WSDL."""
    body = "".join(
        f"<{name}>{escape(format_value(val))}</{name}>" for name, val in params if val is not None
    )
    return (
        '<?xml version="1.0" encoding="utf-8"?>'
        f'<soap:Envelope xmlns:soap="{SOAP_ENV_NS}" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
        'xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
        f'<soap:Body><{method} xmlns="{YUKI_NS}">{body}</{method}></soap:Body>'
        "</soap:Envelope>"
    )


def local(tag: str) -> str:
    """Lokale naam van een (eventueel namespaced) tag."""
    return tag.rsplit("}", 1)[-1]


def parse_response(method: str, xml_text: str | bytes) -> Optional[ET.Element]:
    """Geef het ``<MethodResult>``-element terug, of gooi ``YukiSoapFault``."""
    try:
        root = ET.fromstring(xml_text)
    except ET.ParseError as exc:
        raise YukiError(f"{method}: ongeldig XML-antwoord ({exc})") from exc

    body = next((el for el in root if local(el.tag) == "Body"), None)
    if body is None:
        raise YukiError(f"{method}: geen SOAP Body in antwoord")
    for child in body:
        if local(child.tag) == "Fault":
            code = _child_text(child, "faultcode") or ""
            string = _child_text(child, "faultstring") or ""
            raise YukiSoapFault(method, code, string)

    resp = next((el for el in body if local(el.tag) == f"{method}Response"), None)
    if resp is None:
        raise YukiError(f"{method}: geen {method}Response in antwoord")
    return next((el for el in resp if local(el.tag) == f"{method}Result"), None)


def _child_text(el: ET.Element, name: str) -> Optional[str]:
    for c in el:
        if local(c.tag) == name:
            return (c.text or "").strip()
    return None


def make_ssl_context() -> ssl.SSLContext:
    ctx = ssl.create_default_context()
    ctx.minimum_version = ssl.TLSVersion.TLSv1_2
    return ctx


_SECRET_TAGS = ("accessKey", "sessionID", "sessionId", "clientSecret")


def redact_secrets(xml_text: str) -> str:
    """Vervang accessKey/sessionID/clientSecret in XML door een placeholder."""
    out = xml_text
    for tag in _SECRET_TAGS:
        out = re.sub(fr"<{tag}>.*?</{tag}>", f"<{tag}>[REDACTED]</{tag}>", out, flags=re.DOTALL)
    return out


def maybe_log_raw(service: str, method: str, request_xml: str, response_xml: str) -> None:
    """Schrijf request+response weg als YUKI_LOG_RAW_DIR is gezet.

    Geheimen worden weggelaten. Antwoorden kunnen nog cliëntnamen of bedragen
    bevatten: deze map niet delen of in git zetten.
    """
    raw_dir = os.environ.get("YUKI_LOG_RAW_DIR", "").strip()
    if not raw_dir:
        return
    dest = Path(raw_dir).expanduser()
    try:
        dest.mkdir(parents=True, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
        path = dest / f"{stamp}-{service}-{method}.xml"
        body = (
            f"<!-- {service}.{method} -->\n"
            "<!-- request (geheimen weggelaten) -->\n"
            f"{redact_secrets(request_xml)}\n\n"
            "<!-- response (kan dossiergegevens bevatten; niet delen) -->\n"
            f"{redact_secrets(response_xml)}\n"
        )
        path.write_text(body, encoding="utf-8")
    except OSError as exc:
        log.warning("Kon ruwe SOAP niet wegschrijven naar %s: %s", dest, exc)


class SoapTransport:
    """HTTP-transport voor Yuki SOAP-calls.

    ``http_client`` kan in tests vervangen worden door een ``httpx.Client`` met
    ``httpx.MockTransport``.
    """

    def __init__(
        self,
        api_base: str = DEFAULT_API_BASE,
        http_client: Optional[httpx.Client] = None,
        timeout: float = 60.0,
    ) -> None:
        self.api_base = api_base.rstrip("/")
        self._http = http_client or httpx.Client(verify=make_ssl_context(), timeout=timeout)

    def call(self, service: str, method: str, params: Iterable[Param]) -> Optional[ET.Element]:
        allowed = READ_ONLY_METHODS.get(service)
        if allowed is None:
            raise YukiError(f"Onbekende of niet-toegelaten service: {service}")
        if method not in allowed:
            raise YukiError(f"{service}.{method} is geen toegelaten leesmethode")

        url = f"{self.api_base}/{service}.asmx"
        envelope = build_envelope(method, list(params))
        headers = {
            "Content-Type": "text/xml; charset=utf-8",
            "SOAPAction": f'"{YUKI_NS}{method}"',
        }
        log.debug("SOAP %s.%s", service, method)  # nooit parameters loggen
        try:
            resp = self._http.post(url, content=envelope.encode("utf-8"), headers=headers)
        except httpx.HTTPError as exc:
            raise YukiError(f"{service}.{method}: netwerkfout ({type(exc).__name__})") from exc
        # SOAP 1.1-faults komen met HTTP 500; die parsen we zelf.
        response_text = resp.content.decode("utf-8", errors="replace")
        maybe_log_raw(service, method, envelope, response_text)
        if resp.status_code >= 400 and b"Fault" not in resp.content:
            raise YukiError(f"{service}.{method}: HTTP {resp.status_code}")
        return parse_response(method, resp.content)

    def close(self) -> None:
        self._http.close()
