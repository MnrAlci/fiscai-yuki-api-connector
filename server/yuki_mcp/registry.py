"""Tabel van generieke leestools (XML → JSON) bovenop de uitgebreide allowlist."""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, Optional

SORT = ["ContactAsc", "ContactDesc", "AmountAsc", "AmountDesc", "DateAsc", "DateDesc"]
DOCSORT = ["CreatedDesc", "CreatedAsc", "ModifiedDesc", "ModifiedAsc", "DocumentDateDesc", "DocumentDateAsc",
           "ContactNameAsc", "ContactNameDesc"]


@dataclass
class P:
    name: str
    soap: str
    kind: str = "s"          # s string, d datum, i int, b bool
    req: bool = False
    desc: str = ""
    enum: Optional[list] = None


@dataclass
class G:
    tool: str
    service: str
    method: str                      # of kiesfunctie via pick
    title: str
    desc: str
    scope: str = "admin"             # admin | domain | contact | session
    params: list = field(default_factory=list)
    pag: Optional[tuple] = None      # ("record", "numberOfRecords", "startRecord") | ("page", "pageNumber")
    pick: Optional[Callable[[dict], str]] = None
    methods: tuple = ()
    live: bool = False               # True = al live bevestigd (nooit voor nieuwe methodes)


def _open_period(a):
    kind = "Debtor" if a["soort"] == "debiteuren" else "Creditor"
    return f"Outstanding{kind}WithPaymentReference" if a.get("met_betaalreferentie") else f"Outstanding{kind}ItemsByDate"


def _gl_pick(a):
    return "GLAccountTransactionsFiscal" if a.get("fiscaal") else "GLAccountTransactions"


def _check_pick(a):
    return "CheckOutstandingItemAdmin" if a.get("administratie") else "CheckOutstandingItem"


def _proj_pick(a):
    return "GetProjectsAndID" if a.get("met_id") else "GetProjects"


DT = lambda n, s, r=False, d="": P(n, s, "d", r, d)
# Parameters die volgens de WSDL NA de paginatie-elementen komen (anders dan hun plaats in de parameterlijst).
LATE_AFTER_PAGING = {"GetSuppliersAndCustomers": ("contactType",)}


def order_params(method: str, params: list, extra: list) -> list:
    """Zet de SOAP-elementen in WSDL-volgorde: gewone parameters, paginatie, dan de late parameters."""
    late = [x for x in params if x[0] in LATE_AFTER_PAGING.get(method, ())]
    return [x for x in params if x not in late] + list(extra) + late


FOLDER_PAG = ("record", "numberOfRecords", "startRecord")
SO = P("sortering", "sortOrder", "s", False, "Sortering", DOCSORT)

GENERIC: list[G] = [
    G("yuki_openstaande_posten_periode", "Accounting", "", "Openstaande posten per periode",
      "Openstaande debiteuren- of crediteurenposten met factuurdatum tussen twee data; optioneel met betaalreferentie. "
      "Methodes: Accounting.Outstanding{Debtor|Creditor}ItemsByDate of ...WithPaymentReference.",
      params=[P("soort", "", "s", True, "debiteuren of crediteuren", ["debiteuren", "crediteuren"]),
              P("met_betaalreferentie", "", "b", False, "Gebruik de variant met betaalreferentie"),
              # Volgorde van de SOAP-elementen volgens de WSDL: includeBankTransactions, sortOrder, startDate, endDate.
              P("inclusief_banktransacties", "includeBankTransactions", "b"),
              P("sortering", "sortOrder", "s", False, "Sortering", SORT),
              DT("van", "startDate", True), DT("tot", "endDate", True)],
      pick=_open_period, methods=("OutstandingDebtorItemsByDate", "OutstandingDebtorWithPaymentReference",
                                  "OutstandingCreditorItemsByDate", "OutstandingCreditorWithPaymentReference")),
    G("yuki_grootboektransacties", "Accounting", "", "Grootboektransacties (Accounting)",
      "Transacties van één grootboekrekening in een periode (oudere Accounting-variant; zie ook yuki_grootboekmutaties).",
      params=[P("rekening", "GLAccountCode", "s", True, "Grootboekrekening"), DT("van", "StartDate", True),
              DT("tot", "EndDate", True), P("fiscaal", "", "b", False, "Inclusief fiscale correcties")],
      pick=_gl_pick, methods=("GLAccountTransactions", "GLAccountTransactionsFiscal")),
    G("yuki_controleer_open_post", "Accounting", "", "Controleer openstaande post",
      "Open bedrag van één transactie via factuurnummer of ID (GUID). Zonder administratie: CheckOutstandingItem; "
      "met administratie: CheckOutstandingItemAdmin. Let op: een factuurnummer kan meerdere posten opleveren.",
      scope="admin_opt", params=[P("referentie", "Reference", "s", True, "Factuurnummer of GUID")],
      pick=_check_pick, methods=("CheckOutstandingItem", "CheckOutstandingItemAdmin")),
    G("yuki_domeinen", "Accounting", "Domains", "Domeinen", "Alle domeinen die met deze sleutel bereikbaar zijn.", scope="session"),
    G("yuki_bedrijven", "Accounting", "Companies", "Bedrijven", "Alle beschikbare administraties (Companies).", scope="session"),
    G("yuki_huidig_domein", "Accounting", "GetCurrentDomain", "Huidig domein", "Het huidige Yuki-domein van de sessie.", scope="session"),
    G("yuki_administratie_id", "Accounting", "AdministrationID", "Administratie-ID opzoeken",
      "Administratie-ID (GUID) bij een exacte administratienaam.", scope="session",
      params=[P("administratienaam", "administrationName", "s", True, "Exacte naam")]),
    G("yuki_startbalans", "AccountingInfo", "GetStartBalanceByGlAccount", "Startbalans per rekening",
      "Beginsaldo's per grootboekrekening voor een boekjaar.",
      params=[P("boekjaar", "bookyear", "i", True, "Jaartal"), P("financieel_modus", "financialMode", "i", False, "0 commercieel, 1 fiscaal")]),
    G("yuki_periodetabel", "AccountingInfo", "GetPeriodDateTable", "Startdatum boekjaar",
      "Startdatum van een boekjaar per administratie.", params=[P("jaar_id", "yearID", "i", True, "Boekjaar-ID")]),
    G("yuki_transacties_gepagineerd", "AccountingInfo", "GetTransactions", "Transacties (gepagineerd)",
      "Grootboektransacties met paginering; haalt standaard alle pagina's op (max_paginas begrenst).",
      params=[P("rekening", "glAccountCode", "s", True, "Grootboekrekening"), DT("van", "startDate", True), DT("tot", "endDate", True),
              P("financieel_modus", "financialMode", "i"), P("gegevensgroepen", "dataGroups", "s", False, "Gegevensgroepen (Yuki-syntax)")],
      pag=("record", "numberOfRecords", "startRecord")),
    G("yuki_aangepaste_betaalmethodes", "AccountingInfo", "GetCustomPaymentMethods", "Aangepaste betaalmethodes", "Alle aangepaste betaalmethodes."),
    G("yuki_rgs_schema", "AccountingInfo", "GetRGSScheme", "RGS-rekeningschema",
      "Rekeningschema met RGS-codes (Nederlandse referentie; in België meestal niet gebruikt).",
      scope="admin", params=[P("rgs_versie", "rgsVersion", "s", True, "RGS-versie")]),
    G("yuki_projecten", "AccountingInfo", "", "Projecten", "Projecten (GetProjects of GetProjectsAndID).",
      params=[P("zoekoptie", "searchOption", "s", True, "Zoekoptie", ["All", "Company", "Code", "Description"]),
              P("zoekwaarde", "searchValue", "s"), P("met_id", "", "b", False, "Inclusief project-ID")],
      pick=_proj_pick, methods=("GetProjects", "GetProjectsAndID")),
    G("yuki_projectsaldo", "AccountingInfo", "GetProjectBalance", "Projectsaldo",
      "Saldo van een project per grootboekrekening.",
      params=[P("rekening", "GLAccountCode", "s", True), P("projectcode", "projectCode", "s", True), DT("van", "StartDate", True), DT("tot", "EndDate", True)]),
    G("yuki_contact_standaardwaarden", "AccountingInfo", "GetContactDefaultValues", "Standaardwaarden contact",
      "Standaardwaarden van een contact in een administratie.", params=[P("contact_id", "contactID", "s", True, "Contact-ID (GUID)")]),
    G("yuki_verkoopitems", "Sales", "GetSalesItems", "Verkoopartikelen", "Verkoopartikelen van een administratie."),
    G("yuki_btw_aangiftes", "Vat", "VATReturnList", "Btw-aangiften",
      "Lijst van btw-aangiften voor een jaar (lezen, geen indiening).",
      params=[P("jaar", "year", "i", True), DT("gewijzigd_na", "modifiedAfter")]),
    G("yuki_btw_codes", "Vat", "ActiveVATCodesList", "Actieve btw-codes", "Actieve btw-codes van een administratie."),
    # ---- Backoffice (alleen lezen)
    G("yuki_backoffice_workflow", "Backoffice", "GetWorkflow", "Backoffice-workflow",
      "De workflow (te verwerken documenten) van een administratie (lezen). Het antwoordformaat is niet gedocumenteerd."),
    # ---- Archief (domeinniveau)
    G("yuki_archief_mappen", "Archive", "DocumentFolders", "Archiefmappen", "Alle archiefmappen.", scope="domain"),
    G("yuki_archief_mappen_aantallen", "Archive", "DocumentFolderCounts", "Aantal documenten per map", "Aantallen per map voor een jaar.",
      scope="domain", params=[P("jaar", "year", "i", True)]),
    G("yuki_archief_tabs", "Archive", "DocumentFolderTabs", "Tabs van een map", "Tabs van een archiefmap.", scope="domain",
      params=[P("map_id", "folderID", "s", True)]),
    G("yuki_archief_documenten", "Archive", "Documents", "Documenten (alle)",
      "Documentmetadata, gepagineerd (alleen metadata, geen bestandsinhoud).", scope="domain",
      params=[SO, DT("van", "startDate"), DT("tot", "endDate")], pag=FOLDER_PAG),
    G("yuki_archief_documenten_in_map", "Archive", "DocumentsInFolder", "Documenten in map", "Documentmetadata in een map.", scope="domain",
      params=[P("map_id", "folderID", "i", True), SO, DT("van", "startDate"), DT("tot", "endDate")], pag=FOLDER_PAG),
    G("yuki_archief_documenten_in_tab", "Archive", "DocumentsInTab", "Documenten in tab", "Documentmetadata in een tab.", scope="domain",
      params=[P("tab_id", "tabID", "i", True), SO, DT("van", "startDate"), DT("tot", "endDate")], pag=FOLDER_PAG),
    G("yuki_archief_documenten_per_type", "Archive", "DocumentsByType", "Documenten per type", "Documentmetadata per documenttype.", scope="domain",
      params=[P("documenttype", "documentType", "i", True), SO, DT("van", "startDate"), DT("tot", "endDate")], pag=FOLDER_PAG),
    G("yuki_archief_gewijzigd_per_type", "Archive", "ModifiedDocumentsByType", "Gewijzigde documenten per type", "Sinds een datum gewijzigd.", scope="domain",
      params=[P("documenttype", "documentType", "i", True), SO, DT("gewijzigd_sinds", "modifiedSince", True)], pag=FOLDER_PAG),
    G("yuki_archief_gewijzigd_in_map", "Archive", "ModifiedDocumentsInFolder", "Gewijzigde documenten in map", "Sinds een datum gewijzigd.", scope="domain",
      params=[P("map_id", "folderID", "i", True), SO, DT("gewijzigd_sinds", "modifiedSince", True)], pag=FOLDER_PAG),
    G("yuki_archief_zoeken", "Archive", "SearchDocuments", "Documenten zoeken", "Zoeken in documentmetadata.", scope="domain",
      params=[P("zoekoptie", "searchOption", "s", True, "Zoekoptie", ["All", "Creator", "Contact", "Subject", "Tag", "Type"]),
              P("zoektekst", "searchText", "s", True), P("map_id", "folderID", "i"), P("tab_id", "tabID", "i"), SO,
              DT("van", "startDate"), DT("tot", "endDate")], pag=FOLDER_PAG),
    G("yuki_archief_document", "Archive", "FindDocument", "Document zoeken op ID", "Metadata van één document.", scope="domain",
      params=[P("document_id", "documentID", "s", True)]),
    G("yuki_archief_document_xml", "Archive", "DocumentXMLData", "Document XML-gegevens", "Herkende gegevens (XML) van een document, geen bestand.", scope="domain",
      params=[P("document_id", "documentID", "s", True)]),
    G("yuki_archief_document_paginas", "Archive", "DocumentImageCount", "Aantal pagina's van een document", "Aantal pagina-afbeeldingen.", scope="domain",
      params=[P("document_id", "documentID", "s", True)]),
    G("yuki_archief_betaalmethodes", "Archive", "PaymentMethods", "Betaalmethodes (archief)", "Betaalmethodes.", scope="domain"),
    G("yuki_archief_kostencategorieen", "Archive", "CostCategories", "Kostencategorieën", "Kostencategorieën.", scope="domain"),
    G("yuki_archief_valuta", "Archive", "Currencies", "Valuta's", "Valuta's.", scope="domain"),
    G("yuki_archief_menu", "Archive", "Menu", "Menu", "Menustructuur van het archief.", scope="domain"),
    G("yuki_archief_projecten", "Archive", "Projects", "Projecten (archief)", "Projecten van een administratie.", scope="admin"),
    # ---- Contacten
    G("yuki_contacten_zoeken", "Contact", "SearchContacts", "Contacten zoeken", "Contacten zoeken; gepagineerd.", scope="contact",
      params=[P("zoekoptie", "searchOption", "s", True, "Zoekoptie", ["All", "Name", "City", "Postcode", "Tag", "Email", "Website", "Phone", "Code", "CoCNumber", "VATNumber", "BankAccount", "ID", "ContactType", "HID"]),
              P("zoekwaarde", "searchValue", "s"),
              P("sortering", "sortOrder", "s", False, "Sortering", ["Name", "LastName", "CreatedAsc", "CreatedDesc", "ModifiedAsc", "ModifiedDesc", "HID"]),
              DT("gewijzigd_na", "modifiedAfter"), P("actief", "active", "s", False, "Actief", ["Both", "Active", "Inactive"])],
      pag=("page", "pageNumber")),
    G("yuki_klanten_leveranciers", "Contact", "GetSuppliersAndCustomers", "Klanten en leveranciers", "Klanten en/of leveranciers; gepagineerd.", scope="contact",
      params=[P("zoekoptie", "searchOption", "s", True, "Zoekoptie", ["All", "Name", "City", "Postcode", "Tag", "Email", "Website", "Phone", "Code", "CoCNumber", "VATNumber", "BankAccount", "ID", "ContactType", "HID"]),
              P("zoekwaarde", "searchValue", "s"),
              P("sortering", "sortOrder", "s", False, "Sortering", ["Name", "LastName", "CreatedAsc", "CreatedDesc", "ModifiedAsc", "ModifiedDesc", "HID"]),
              DT("gewijzigd_na", "modifiedAfter"), P("actief", "active", "s", False, "Actief", ["Both", "Active", "Inactive"]),
              P("contacttype", "contactType", "s", False, "Type", ["Customer", "Supplier", "Both", "None"])],
      pag=("page", "pageNumber")),
]


def all_methods(g: G) -> tuple:
    return g.methods or (g.method,)
