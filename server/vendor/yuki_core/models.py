"""Dataclasses + tolerante parsers voor Yuki-antwoorden.

Veel Accounting-methodes geven een vrij XML-fragment terug (``<xs:any>`` in de
WSDL); de exacte element-/attribuutnamen staan niet in de WSDL. De parsers
zoeken daarom hoofdletterongevoelig in attributen én kindelementen, met een
lijst kandidaat-namen. AccountingInfo-methodes zijn wél getypeerd in de WSDL
(GlAccount, TransactionInfo, AccountStartBalance, AdministrationPeriod).
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal, InvalidOperation
from typing import Iterable, Optional
from xml.etree import ElementTree as ET

from .soap import local


# ------------------------------------------------------------------ helpers
def find_value(el: ET.Element, *names: str) -> Optional[str]:
    """Waarde van het eerste attribuut of direct kindelement met een van ``names``."""
    wanted = [n.lower() for n in names]
    attrs = {local(k).lower(): v for k, v in el.attrib.items()}
    children = {}
    for c in el:
        children.setdefault(local(c.tag).lower(), c)
    for n in wanted:
        if n in attrs:
            return attrs[n].strip()
        if n in children:
            c = children[n]
            if c.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
                return None
            return (c.text or "").strip()
    return None


def to_decimal(value: Optional[str]) -> Optional[Decimal]:
    if value is None or value == "":
        return None
    try:
        return Decimal(value.replace(",", ".") if value.count(",") == 1 and "." not in value else value)
    except InvalidOperation:
        return None


def to_datetime(value: Optional[str]) -> Optional[datetime]:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def iter_records(result: Optional[ET.Element], record_names: Iterable[str]) -> list[ET.Element]:
    """Alle elementen (op elke diepte) waarvan de lokale naam in ``record_names`` staat."""
    if result is None:
        return []
    names = {n.lower() for n in record_names}
    return [el for el in result.iter() if el is not result and local(el.tag).lower() in names]


# ----------------------------------------------------------- dataclasses
def to_bool(value: Optional[str]) -> Optional[bool]:
    if value is None or value == "":
        return None
    v = value.strip().lower()
    if v in ("true", "1", "yes"):
        return True
    if v in ("false", "0", "no"):
        return False
    return None


@dataclass(frozen=True)
class Administration:
    id: str
    name: str
    internal_customer_code: Optional[str] = None
    domain_id: Optional[str] = None
    vat: Optional[str] = None
    coc: Optional[str] = None
    active: Optional[bool] = None


@dataclass(frozen=True)
class GLLine:
    code: str
    name: Optional[str] = None
    debit: Optional[Decimal] = None
    credit: Optional[Decimal] = None
    balance: Optional[Decimal] = None


@dataclass(frozen=True)
class OpenItem:
    contact: Optional[str]
    contact_code: Optional[str]
    reference: Optional[str]
    description: Optional[str]
    date: Optional[datetime]
    due_date: Optional[datetime]
    original_amount: Optional[Decimal]
    open_amount: Optional[Decimal]
    raw: dict = field(default_factory=dict, compare=False, repr=False)


@dataclass(frozen=True)
class Transaction:
    id: Optional[str]
    date: Optional[datetime]
    description: Optional[str]
    amount: Optional[Decimal]
    gl_account_code: Optional[str]
    contact: Optional[str] = None
    document_reference: Optional[str] = None


@dataclass(frozen=True)
class NetRevenue:
    van: datetime
    tot: datetime
    fiscaal: bool
    amount: Decimal


# ---------------------------------------------------------------- parsers
def parse_administrations(result: Optional[ET.Element]) -> list[Administration]:
    out: list[Administration] = []
    for rec in iter_records(result, ["Administration"]):
        admin_id = find_value(rec, "ID", "Id", "AdministrationID", "administration_id")
        name = find_value(rec, "Name", "AdministrationName")
        if admin_id and name is not None:
            out.append(Administration(
                admin_id, name,
                find_value(rec, "InternalCustomerCode", "CustomerCode") or None,
                find_value(rec, "DomainID", "DomainId", "domain_id") or None,
                find_value(rec, "VAT", "Vat", "VatNumber", "vat") or None,
                find_value(rec, "CoC", "COC", "Coc", "coc", "ChamberOfCommerce") or None,
                to_bool(find_value(rec, "Active", "active")),
            ))
    return out


def parse_gl_balance(result: Optional[ET.Element]) -> list[GLLine]:
    lines: list[GLLine] = []
    for rec in iter_records(result, ["GLAccount", "GlAccount", "Account", "GLAccountBalance"]):
        if rec is result:
            continue
        code = find_value(rec, "code", "GLAccountCode", "AccountCode")
        if not code:
            continue
        debit = to_decimal(find_value(rec, "Debit", "AmountDebit"))
        credit = to_decimal(find_value(rec, "Credit", "AmountCredit"))
        balance = to_decimal(find_value(rec, "Amount", "Balance", "Saldo"))
        if balance is None and (debit is not None or credit is not None):
            balance = (debit or Decimal(0)) - (credit or Decimal(0))
        lines.append(GLLine(code, find_value(rec, "Description", "Name", "descripton"),
                            debit, credit, balance))
    return lines


def parse_open_items(result: Optional[ET.Element]) -> list[OpenItem]:
    items: list[OpenItem] = []
    for rec in iter_records(result, ["Item", "OutstandingItem"]):
        raw = {local(k): v for k, v in rec.attrib.items()}
        raw.update({local(c.tag): (c.text or "").strip() for c in rec if len(c) == 0})
        items.append(OpenItem(
            contact=find_value(rec, "Contact", "ContactName", "FullName"),
            contact_code=find_value(rec, "ContactCode", "Code"),
            reference=find_value(rec, "Reference", "InvoiceReference", "PaymentReference"),
            description=find_value(rec, "Description"),
            date=to_datetime(find_value(rec, "Date", "InvoiceDate", "TransactionDate")),
            due_date=to_datetime(find_value(rec, "DueDate", "ExpiryDate")),
            original_amount=to_decimal(find_value(rec, "OriginalAmount", "Amount")),
            open_amount=to_decimal(find_value(rec, "OpenAmount", "OutstandingAmount", "Open")),
            raw=raw,
        ))
    return items


def parse_transaction_details(result: Optional[ET.Element]) -> list[Transaction]:
    """AccountingInfo.GetTransactionDetails → ArrayOfTransactionInfo."""
    return [
        Transaction(
            id=find_value(rec, "id"),
            date=to_datetime(find_value(rec, "transactionDate")),
            description=find_value(rec, "description"),
            amount=to_decimal(find_value(rec, "transactionAmount")),
            gl_account_code=find_value(rec, "glAccountCode"),
            contact=find_value(rec, "fullName"),
            document_reference=find_value(rec, "documentReference"),
        )
        for rec in iter_records(result, ["TransactionInfo"])
    ]


def parse_decimal_result(result: Optional[ET.Element]) -> Decimal:
    value = to_decimal((result.text or "").strip() if result is not None else None)
    return value if value is not None else Decimal(0)


def parse_gl_scheme(result: Optional[ET.Element]) -> list[GLLine]:
    """AccountingInfo.GetGLAccountScheme → codes + omschrijving (let op: WSDL-typo 'descripton')."""
    return [
        GLLine(code=find_value(rec, "code") or "",
               name=find_value(rec, "descriptionNL", "descripton", "descriptionFR", "descriptionEN"))
        for rec in iter_records(result, ["GlAccount"])
    ]
