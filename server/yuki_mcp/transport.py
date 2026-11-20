"""SOAP-transport met uitgebreide, uitsluitend-lezen allowlist (pluginlaag)."""
from __future__ import annotations

from typing import Iterable, Optional
from xml.etree import ElementTree as ET

import httpx

from yuki_core.errors import YukiError
from yuki_core.soap import (Param, SoapTransport, YUKI_NS, build_envelope, maybe_log_raw,
                                parse_response, READ_ONLY_METHODS)

# Leesmethodes volgens de officiële Yuki-documentatie (api.yukiworks.be/ws), die de
# kernclient (alleen Accounting + AccountingInfo) niet kent.
EXTRA_READ_METHODS: dict[str, frozenset[str]] = {
    "Accounting": frozenset({
        "Companies", "CheckOutstandingItem", "CheckOutstandingItemAdmin",
        "OutstandingCreditorItemsByDate", "OutstandingCreditorWithPaymentReference",
        "OutstandingDebtorItemsByDate", "OutstandingDebtorItemsWithLanguage",
        "OutstandingDebtorWithPaymentReference",
    }),
    "AccountingInfo": frozenset({
        "Companies", "Domains", "AdministrationID", "GetCurrentDomain",
        "GetContactDefaultValues", "GetCustomPaymentMethods", "GetProjectBalance",
        "GetProjects", "GetProjectsAndID", "GetRGSScheme",
    }),
    "Archive": frozenset({
        "DocumentFolders", "DocumentFolderCounts", "DocumentFolderTabs", "Documents",
        "DocumentsInFolder", "DocumentsInTab", "FindDocument", "DocumentsByType",
        "ModifiedDocumentsByType", "ModifiedDocumentsInFolder", "SearchDocuments",
        "DocumentXMLData", "DocumentImageCount", "PaymentMethods", "CostCategories",
        "Currencies", "Menu", "Projects",
    }),
    "Sales": frozenset({"GetSalesItems"}),
    "Backoffice": frozenset({"GetWorkflow"}),
    "Contact": frozenset({"SearchContacts", "GetSuppliersAndCustomers"}),
    "Vat": frozenset({"VATReturnList", "ActiveVATCodesList"}),
}

# Bewust NIET toegelaten (reden in README): schrijven, sessiestatus wijzigen of binaire inhoud.
EXCLUDED_METHODS: dict[str, str] = {
    "ProcessJournal": "schrijft boekingen",
    "ProcessSalesInvoices": "schrijft verkoopfacturen",
    "ProcessRecognizedSalesInvoices": "schrijft verkoopfacturen",
    "ProcessPurchaseInvoices": "schrijft aankoopfacturen",
    "UpdateContact": "wijzigt contacten",
    "UploadDocument": "uploadt documenten",
    "UploadDocumentWithData": "uploadt documenten",
    "UploadDocumentWithAttachment": "uploadt documenten",
    "SetCurrentDomain": "wijzigt de sessiestatus",
    "SetLanguage": "wijzigt de sessiestatus",
    "AuthenticateByUserName": "wachtwoordlogin; alleen sleutel toegelaten",
    "AuthenticateClient": "niet nodig; alleen sleutel toegelaten",
    "GLAccountTransactionsAndContact": "door Yuki als verouderd (obsolete) aangemerkt",
    "GetTransactionDocument": "binaire inhoud (vertrouwelijk, te groot voor chat)",
    "DocumentBinaryData": "binaire inhoud (vertrouwelijk, te groot voor chat)",
    "DocumentFile": "binaire inhoud (vertrouwelijk, te groot voor chat)",
    "DocumentImage": "binaire inhoud (vertrouwelijk, te groot voor chat)",
    "DocumentBundle": "binaire inhoud (vertrouwelijk, te groot voor chat)",
    "DocumentDownloadUrl": "geeft een downloadlink naar een document",
    "DocumentXMLDataAsBinary": "binaire variant van DocumentXMLData",
    "DocumentXMLDataAsString": "dubbel met DocumentXMLData",
    "SalesInvoiceSchemaPath": "geen gegevens (schemapad)",
    "PurchaseInvoiceSchemaPath": "geen gegevens (schemapad)",
    "Language": "sessie-instelling, geen gegevens",
    "SupportedLanguages": "sessie-instelling, geen gegevens",
}

ALLOWED: dict[str, frozenset[str]] = {
    s: frozenset(READ_ONLY_METHODS.get(s, frozenset()) | EXTRA_READ_METHODS.get(s, frozenset()))
    for s in set(READ_ONLY_METHODS) | set(EXTRA_READ_METHODS)
}

WRITE_PREFIXES = ("Process", "Upload", "Update", "Set", "Delete", "Create", "Add", "Remove", "Save")


def is_allowed(service: str, method: str) -> bool:
    if method in EXCLUDED_METHODS or method.startswith(WRITE_PREFIXES):
        return False
    return method in ALLOWED.get(service, frozenset())


# Enige uitzondering op "alleen lezen-methodes": SetCurrentDomain wijzigt alleen de sessiecontext (huidig domein)
# en schrijft geen boekhoudgegevens. Een accountantssleutel heeft geen huidig domein; Archive- en Contact-calls
# vragen er één. Alleen intern toegankelijk via ``allow_set_domain()``; nooit als tool.
_SET_DOMAIN = ("Accounting", "SetCurrentDomain")
# Tweede, strikt afgebakende uitzondering: de boekingsworkflow (standaard UIT). Alleen Accounting.ProcessJournal, alleen binnen
# ``allow_journal_write()`` en alleen als YUKI_WRITE_ENABLED=ja. Officieel gedocumenteerd: api.yukiworks.be/ws/Accounting.asmx?op=ProcessJournal.
_JOURNAL = ("Accounting", "ProcessJournal")


class RawXml(str):
    """Waarde die zonder escaping als XML-fragment in de SOAP-body komt (voor xmlDoc)."""


def _write_enabled() -> bool:
    import os
    return os.environ.get("YUKI_WRITE_ENABLED", "").strip().lower() == "ja"


def build_plugin_envelope(method: str, params) -> str:
    from xml.sax.saxutils import escape
    from yuki_core.soap import SOAP_ENV_NS, format_value
    body = "".join(
        f"<{n}>{v if isinstance(v, RawXml) else escape(format_value(v))}</{n}>" for n, v in params if v is not None)
    return ('<?xml version="1.0" encoding="utf-8"?>'
            f'<soap:Envelope xmlns:soap="{SOAP_ENV_NS}" xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" '
            'xmlns:xsd="http://www.w3.org/2001/XMLSchema">'
            f'<soap:Body><{method} xmlns="{YUKI_NS}">{body}</{method}></soap:Body></soap:Envelope>')


class PluginTransport(SoapTransport):
    """Zelfde SOAP-laag, maar met de uitgebreide leesallowlist; schrijven blijft geweigerd."""

    _allow_set_domain = False
    _allow_journal = False

    def allow_journal_write(self):
        import contextlib

        @contextlib.contextmanager
        def _cm():
            if not _write_enabled():
                raise YukiError("Schrijven staat uit: zet YUKI_WRITE_ENABLED=ja om de boekingsworkflow te activeren.")
            self._allow_journal = True
            try:
                yield
            finally:
                self._allow_journal = False
        return _cm()

    def allow_set_domain(self):
        import contextlib

        @contextlib.contextmanager
        def _cm():
            self._allow_set_domain = True
            try:
                yield
            finally:
                self._allow_set_domain = False
        return _cm()

    def call(self, service: str, method: str, params: Iterable[Param]) -> Optional[ET.Element]:
        if service not in ALLOWED:
            raise YukiError(f"Onbekende of niet-toegelaten service: {service}")
        if (service, method) == _SET_DOMAIN and self._allow_set_domain:
            pass
        elif (service, method) == _JOURNAL and self._allow_journal and _write_enabled():
            pass
        elif not is_allowed(service, method):
            raise YukiError(f"{service}.{method} is geen toegelaten leesmethode")
        url = f"{self.api_base}/{service}.asmx"
        envelope = build_plugin_envelope(method, list(params))
        headers = {"Content-Type": "text/xml; charset=utf-8", "SOAPAction": f'"{YUKI_NS}{method}"'}
        # Optionele nieuwe poging (YUKI_MAX_RETRIES, standaard 0 = uit, maximum 5) alleen bij netwerkfouten en alleen voor leesmethodes.
        import os
        import random
        import time
        retries = 0 if (service, method) in (_JOURNAL, _SET_DOMAIN) else max(0, min(5, int(os.environ.get("YUKI_MAX_RETRIES", "0") or 0)))
        attempt = 0
        while True:
            try:
                resp = self._http.post(url, content=envelope.encode("utf-8"), headers=headers)
                break
            except httpx.TransportError as exc:
                if attempt >= retries:
                    raise YukiError(f"{service}.{method}: netwerkfout ({type(exc).__name__})") from exc
                time.sleep(min(8.0, 0.5 * (2 ** attempt)) * (0.5 + random.random() / 2))
                attempt += 1
            except httpx.HTTPError as exc:
                raise YukiError(f"{service}.{method}: netwerkfout ({type(exc).__name__})") from exc
        text = resp.content.decode("utf-8", errors="replace")
        maybe_log_raw(service, method, envelope, text)
        if resp.status_code >= 400 and b"Fault" not in resp.content:
            raise YukiError(f"{service}.{method}: HTTP {resp.status_code}")
        return parse_response(method, resp.content)
