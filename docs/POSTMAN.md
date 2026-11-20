# Postman collection (file-based)

> **Not an official Yuki or Visma product.** This is a complementary, read-only collection aligned to the plugin. Yuki publishes its own official Postman documentation (see below). Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

## Official reference

Yuki publishes the **official** documentation of its 13 web services as a Postman documentation page: [Yuki API Webservices Documentation](https://documenter.getpostman.com/view/12207912/UVCBB51L). Use it as the authoritative reference for every method, parameter and response. Our collection does not replace it: it is a smaller, **read-only** set aligned to this plugin's allow-list, with an environment template, a session test script and a disabled folder for write calls. It is not an official Yuki or Visma product.

The collection lets you try the same **read** calls the plugin uses, directly against the Yuki web services, to understand or debug an answer. It is file-based: import the two JSON files into Postman (or any tool that reads Postman v2.1 collections). Do not use a Postman cloud workspace for real client data.

## Files
- `postman/FISCAi-Yuki-API-Connector.postman_collection.json` (collection v2.1, 63 requests)
- `postman/FISCAi-Yuki-API-Connector.postman_environment.json` (environment template, placeholders only)

## Set up
1. Import both files (Postman: Import, then select the files).
2. Select the environment "FISCAi Yuki API Connector (template)".
3. Fill `yuki_access_key` as a **secret** variable in the *current value* column, on your own computer. Never commit or share it. Fill `administration_id` after step 5.
4. Adjust `start_date`, `end_date`, `as_of_date` (the shipped values are `[Voorbeeld]` dates). `base_url` is the public Yuki endpoint `https://api.yukiworks.be/ws`.
5. Run **00 Authentication / Accounting.Authenticate**. Its test script stores the session id in the collection variable `session_id` (it never prints it). Then run **Accounting.Administrations** and copy the id you need into `administration_id`.
6. Run any read request. Calls count against your Yuki daily quota (the plugin uses a limit of 900 per domain per day); be sparing.

## Groups
One folder per Yuki service: `Accounting`, `AccountingInfo`, `Archive`, `Backoffice`, `Contact`, `Sales`, `Vat`. They contain exactly the read methods in the plugin's allow-list (accounting and info reads, archive metadata reads, outstanding items, VAT lists). Archive and Contact calls need a current domain when you use an accountant (portal) key; set it with the disabled `SetCurrentDomain` request after explicit approval, or use a domain key.

## Disabled folder
`99 DISABLED - requires explicit approval` holds `SetCurrentDomain` (session context only) and `ProcessJournal` (a **write**). They are there for reference only. Do not run them without explicit approval. Workflow documents are never booked as journal entries; finish them with **Afhandelen** in Yuki.

## Notes and limits
- Request bodies were built from the plugin's own registry and SOAP client (SOAP 1.1, namespace `http://www.theyukicompany.com/`, header `SOAPAction`). They were cross-checked against the [official Postman documentation](https://documenter.getpostman.com/view/12207912/UVCBB51L) and the public WSDL files (`https://api.yukiworks.be/ws/<Service>.asmx?WSDL`) on 2026-11-20: element names match for the requests that the official collection also contains. That check found the element order wrong for four period-based outstanding-item requests and for `GetSuppliersAndCustomers`; both the collection and the plugin now follow the WSDL order. A few read methods in our collection (for example `GetFinancialYearModifiedDate`, `GetContactDefaultValues`, `GetSalesItems`, `Projects`) have no example in the official collection; for those the WSDL is the reference. Verify each method against the official documentation (link in each request description); it can change.
- All values are placeholders or `[Voorbeeld]`. No real key, domain or client data is included.
- The session id is a secret; do not export the collection after authenticating with real data without clearing `session_id`.
