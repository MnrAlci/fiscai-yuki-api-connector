# Postman-collectie (op bestand)

> **Geen officieel product van Yuki of Visma.** Dit is een aanvullende, alleen-lezen collectie, afgestemd op de plugin. Yuki publiceert zelf officiële Postman-documentatie (zie hieronder). Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

## Officiële referentie

Yuki publiceert de **officiële** documentatie van zijn 13 webservices als Postman-documentatiepagina: [Yuki API Webservices Documentation](https://documenter.getpostman.com/view/12207912/UVCBB51L). Gebruik die als gezaghebbende referentie voor elke methode, parameter en respons. Onze collectie vervangt ze niet: het is een kleinere, **alleen-lezen** set, afgestemd op de allowlist van deze plugin, met een omgevingssjabloon, een sessie-testscript en een uitgeschakelde map voor schrijfacties. Het is geen officieel product van Yuki of Visma.

Met de collectie probeert u dezelfde **leesaanroepen** als de plugin rechtstreeks op de Yuki-webservices, om een antwoord te begrijpen of te onderzoeken. Alles werkt via bestanden: importeer de twee JSON-bestanden in Postman (of een tool die Postman v2.1 leest). Gebruik voor echte klantgegevens geen Postman-cloudwerkruimte.

## Bestanden
- `postman/FISCAi-Yuki-API-Connector.postman_collection.json` (collectie v2.1, 63 aanvragen)
- `postman/FISCAi-Yuki-API-Connector.postman_environment.json` (omgevingssjabloon, alleen plaatshouders)

## Instellen
1. Importeer beide bestanden.
2. Kies de omgeving "FISCAi Yuki API Connector (template)".
3. Vul `yuki_access_key` als **geheime** variabele in de kolom *huidige waarde*, op uw eigen computer. Nooit committen of delen. Vul `administration_id` na stap 5.
4. Pas `start_date`, `end_date`, `as_of_date` aan (de meegeleverde waarden zijn `[Voorbeeld]`-datums). `base_url` is het publieke Yuki-eindpunt `https://api.yukiworks.be/ws`.
5. Voer **00 Authentication / Accounting.Authenticate** uit. Het testscript bewaart de sessie in de collectievariabele `session_id` (zonder die te tonen). Voer daarna **Accounting.Administrations** uit en kopieer het gewenste id naar `administration_id`.
6. Voer een leesaanvraag uit. Elke call telt mee voor uw dagquotum bij Yuki (de plugin hanteert 900 per domein per dag); ga er zuinig mee om.

## Groepen
Eén map per Yuki-service: `Accounting`, `AccountingInfo`, `Archive`, `Backoffice`, `Contact`, `Sales`, `Vat`, met precies de leesmethodes uit de allowlist van de plugin. Archive- en Contact-calls vragen met een accountantssleutel (portaal) een huidig domein: stel dat in via de uitgeschakelde `SetCurrentDomain`-aanvraag na uitdrukkelijke toestemming, of gebruik een domeinsleutel.

## Uitgeschakelde map
`99 DISABLED - requires explicit approval` bevat `SetCurrentDomain` (alleen sessiecontext) en `ProcessJournal` (een **schrijfactie**), enkel ter referentie. Niet uitvoeren zonder uitdrukkelijke toestemming. Workflowdocumenten worden nooit als boeking verwerkt; handel ze af met **Afhandelen** in Yuki.

## Opmerkingen
- De aanvragen zijn opgebouwd uit het eigen register en de SOAP-client van de plugin (SOAP 1.1, namespace `http://www.theyukicompany.com/`, header `SOAPAction`). Ze zijn op 2026-11-20 nagekeken tegen de [officiële Postman-documentatie](https://documenter.getpostman.com/view/12207912/UVCBB51L) en de publieke WSDL-bestanden (`https://api.yukiworks.be/ws/<Service>.asmx?WSDL`): de elementnamen komen overeen voor de aanvragen die ook in de officiële collectie staan. Daarbij bleek de volgorde van de elementen fout bij vier periodegebonden openstaande-postenaanvragen en bij `GetSuppliersAndCustomers`; zowel de collectie als de plugin volgen nu de WSDL-volgorde. Enkele leesmethodes in onze collectie (bv. `GetFinancialYearModifiedDate`, `GetContactDefaultValues`, `GetSalesItems`, `Projects`) hebben geen voorbeeld in de officiële collectie; daar is de WSDL de referentie. Controleer elke methode in de officiële documentatie (link in de beschrijving van elke aanvraag); die kan wijzigen.
- Alle waarden zijn plaatshouders of `[Voorbeeld]`. Geen echte sleutel, domein of klantgegevens.
- De sessie-id is geheim: exporteer de collectie niet na echt gebruik zonder `session_id` te wissen.
