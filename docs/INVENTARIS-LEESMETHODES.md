# Inventaris leesmethodes

Bron: de publieke helppagina's en WSDL's van de Yuki-webservices (api.yukiworks.be/ws), geraadpleegd op 20/11/2026. Services: Accounting, AccountingInfo, Archive, Sales, Purchase, Contact, Vat. Er is geen enkele methode live getest in deze build; nieuwe methodes zijn alleen met een mock getest.

## Reeds toegelaten door de kernclient (Accounting en AccountingInfo)

- **Accounting**: AdministrationID, Administrations, AdministrationsWithInternalCustomerCode, Authenticate, Domains, GLAccountBalance, GLAccountBalanceFiscal, GLAccountBalanceYearEnd, GLAccountTransactions, GLAccountTransactionsFiscal, GetCurrentDomain, NetRevenue, NetRevenueFiscal, OutstandingCreditorItems, OutstandingCreditorItemsByDateOutstanding, OutstandingDebtorItems, OutstandingDebtorItemsByDateOutstanding
- **AccountingInfo**: Administrations, AdministrationsWithInternalCustomerCode, Authenticate, GetFinancialYearModifiedDate, GetGLAccountScheme, GetPeriodDateTable, GetStartBalanceByGlAccount, GetTransactionDetails, GetTransactions

## Toegevoegd in de pluginlaag (alleen lezen)

- **Accounting**: CheckOutstandingItem, CheckOutstandingItemAdmin, Companies, OutstandingCreditorItemsByDate, OutstandingCreditorWithPaymentReference, OutstandingDebtorItemsByDate, OutstandingDebtorItemsWithLanguage, OutstandingDebtorWithPaymentReference
- **AccountingInfo**: AdministrationID, Companies, Domains, GetContactDefaultValues, GetCurrentDomain, GetCustomPaymentMethods, GetProjectBalance, GetProjects, GetProjectsAndID, GetRGSScheme
- **Archive**: CostCategories, Currencies, DocumentFolderCounts, DocumentFolderTabs, DocumentFolders, DocumentImageCount, DocumentXMLData, Documents, DocumentsByType, DocumentsInFolder, DocumentsInTab, FindDocument, Menu, ModifiedDocumentsByType, ModifiedDocumentsInFolder, PaymentMethods, Projects, SearchDocuments
- **Sales**: GetSalesItems
- **Backoffice**: GetWorkflow
- **Contact**: GetSuppliersAndCustomers, SearchContacts
- **Vat**: ActiveVATCodesList, VATReturnList

## Bewust niet toegevoegd

| Methode | Reden |
|---|---|
| AuthenticateByUserName | wachtwoordlogin; alleen sleutel toegelaten |
| AuthenticateClient | niet nodig; alleen sleutel toegelaten |
| DocumentBinaryData | binaire inhoud (vertrouwelijk, te groot voor chat) |
| DocumentBundle | binaire inhoud (vertrouwelijk, te groot voor chat) |
| DocumentDownloadUrl | geeft een downloadlink naar een document |
| DocumentFile | binaire inhoud (vertrouwelijk, te groot voor chat) |
| DocumentImage | binaire inhoud (vertrouwelijk, te groot voor chat) |
| DocumentXMLDataAsBinary | binaire variant van DocumentXMLData |
| DocumentXMLDataAsString | dubbel met DocumentXMLData |
| GLAccountTransactionsAndContact | door Yuki als verouderd (obsolete) aangemerkt |
| GetTransactionDocument | binaire inhoud (vertrouwelijk, te groot voor chat) |
| Language | sessie-instelling, geen gegevens |
| ProcessJournal | schrijft boekingen |
| ProcessPurchaseInvoices | schrijft aankoopfacturen |
| ProcessRecognizedSalesInvoices | schrijft verkoopfacturen |
| ProcessSalesInvoices | schrijft verkoopfacturen |
| PurchaseInvoiceSchemaPath | geen gegevens (schemapad) |
| SalesInvoiceSchemaPath | geen gegevens (schemapad) |
| SetCurrentDomain | wijzigt de sessiestatus |
| SetLanguage | wijzigt de sessiestatus |
| SupportedLanguages | sessie-instelling, geen gegevens |
| UpdateContact | wijzigt contacten |
| UploadDocument | uploadt documenten |
| UploadDocumentWithAttachment | uploadt documenten |
| UploadDocumentWithData | uploadt documenten |

Schrijfmethodes (Process*, Upload*, Update*, Set*) worden ook op prefix geweigerd, zelfs als iemand ze in de allowlist zou zetten. Enige uitzondering: Accounting.ProcessJournal voor de boekingsworkflow, alleen met YUKI_WRITE_ENABLED=ja en binnen de boekingstool (zie BOEKINGSWORKFLOW.md).

---

Powered by FISCALCI Accounting & Tax (Askin Alci)
