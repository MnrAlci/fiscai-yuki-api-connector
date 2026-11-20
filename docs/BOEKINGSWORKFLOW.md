# Boekingsworkflow (optioneel, standaard UIT)

**Boeken in Yuki betekent: backoffice-status 'Afgehandeld'.** Workflowdocumenten (aankoop- of verkoopfacturen) handel je af in de Yuki-backoffice via 'Afhandelen' in de Yuki-backoffice (de gebruiker of een eigen procedure); deze plugin weigert ze als journaalpost (harde blokkade: een journaalpost geeft een dubbele kost). `ProcessJournal` blijft enkel voor echte memoriaalposten (bron wachtrekening).

**Scope.** Bedoeld voor Belgische boekhouders/accountants: voorstellen volgen het Belgische minimum algemeen rekeningstelsel (MAR) en het Belgische btw-stelsel (tarieven 21 %, 12 %, 6 % en 0 %; verifieer actuele regel). Gebruik buiten België: verifieer zelf de lokale regels. Er staan geen wetsartikelen in deze plugin; voor wettelijke vragen: verifieer actuele regel bij de officiële bron (FOD Financiën, Belgisch Staatsblad).

## Veiligheid in het kort
- **Standaard uit.** Alleen `YUKI_WRITE_ENABLED=ja` zet het aan. Elke andere waarde (ook `true`, `1`) laat het uit. Uit = de vier tools geven alleen een instructietekst; er gaat geen enkele call naar Yuki.
- **Eén schrijfmethode:** `Accounting.ProcessJournal`. Geen andere schrijfmethode is bereikbaar; de transportlaag weigert ze, en weigert ook ProcessJournal buiten de boekingstool of zonder de schakelaar.
- **Eén boeking per bevestiging.** `yuki_boeking_voorstel` geeft een eenmalig token (standaard 15 minuten geldig, instelbaar 1 tot 60) dat gebonden is aan exact dat voorstel (administratie + SHA-256 van de journaal-XML). Een nieuw voorstel maakt het vorige token ongeldig. Hergebruik, een andere administratie, een afwijkende hash of een verlopen token wordt geweigerd. Het token wordt vóór het versturen verbruikt: ook na een fout is een nieuw voorstel nodig.
- **Geen bulk, geen automatische boekingen.** `token` is een string; lijsten worden geweigerd. De gebruiker bevestigt elke boeking uitdrukkelijk (`bevestiging='ja'`).
- **Dry-run:** `dry_run=true` toont de exacte XML en SOAP-body (sessie verborgen) zonder te boeken; het token blijft geldig.
- **Dagmaximum** (`YUKI_WRITE_MAX_PER_DAY`, standaard 25, maximum 100) en elke schrijfcall telt mee in de Yuki-daglimiet.
- **Auditlog** (lokaal, 0600, `boekingen-audit.jsonl` in de datamap): tijd, administratie, item, hash, boekingsregels, uitkomst. Nooit sleutels of sessies.
- **Toolannotaties:** `yuki_boeking_bevestigen` = readOnlyHint false, destructiveHint true. `yuki_boeking_voorstel` schrijft alleen een lokaal token.

## Werking
1. `yuki_boeking_voorstel` met `bron` (bij `documentworkflow` krijg je het voorstel en de dubbelcontrole als invoer voor het afhandelen in de backoffice, maar nooit een token):
   - `documentworkflow`: documenten uit een archiefmap (`map_id`, zie `yuki_archief_mappen`), één per keer.
   - `wachtrekening`: boekingen op de wachtrekening die u opgeeft (bv. MAR 499; Yuki-specifiek en uw eigen keuze). Regels die al met een gelijk en tegengesteld bedrag verrekend zijn, worden niet voorgesteld.
   Reeds geboekte of overgeslagen items verschijnen niet opnieuw (lokale status). Met `aanpassingen` past u het voorstel aan (type, rekening, btw_code, btw_aftrek, relatie, bedrag_incl, datum, omschrijving, referentie).
2. Voorstel: rekening, btw-code, relatie, bedrag, omschrijving. Voorgestelde standaardrekeningen volgens MAR: 440000 leveranciers, 400000 klanten, 411000 btw te vorderen, 451000 te betalen btw. Elke rekening wordt gecontroleerd tegen het rekeningschema van de administratie; ontbreekt ze, dan is er geen token. Het voorstel blijft onvolledig (geen token) zolang rekening, relatie of bedrag ontbreken.
3. De gebruiker antwoordt of past aan; de assistent vraagt een nieuw voorstel.
4. Pas na uitdrukkelijke bevestiging: `yuki_boeking_bevestigen` met token, voorstel_hash en `bevestiging='ja'`.
5. `yuki_boeking_overslaan` slaat een item lokaal over; `yuki_boeking_status` toont de stand.

Btw wordt geboekt via de grootboekrekeningen (411000/451000): het journaalformaat van Yuki heeft geen btw-codeveld. De btw-code in het voorstel bepaalt het percentage; controleer de btw-aangifte in Yuki achteraf.

## Kantoorregels

Deze editie past geen kantoorspecifieke regels toe: u bepaalt zelf rekening en btw-aftrek (verifieer actuele regel).

## Controle op dubbele boekingen (altijd vóór een token)
Vóór elk voorstel leest de plugin met `AccountingInfo.GetTransactionDetails` de boekingen op de relatierekening (bv. 440000 of 400000) in een venster van ±45 dagen rond de documentdatum (uitgelijnd op maandgrenzen, met cache: zuinig met calls). Uitkomst per item:
- **geen bestaande boeking gevonden**: token mogelijk.
- **mogelijk al geboekt** (met reden en zekerheid laag/midden): zelfde bedrag en zelfde relatie of datum; zelfde referentie met ander bedrag; of zelfde bedrag met tegengesteld teken (creditnota, terugboeking of betaling).
- **al geboekt** (zekerheid hoog): zelfde bedrag en zelfde referentie/factuurnummer, of zelfde bedrag, relatie en documentdatum, of het document is via de documentreferentie al aan een transactie gekoppeld.
- **controle niet uitgevoerd** (fout, limiet): behandeld als geblokkeerd.
Bij alles behalve de eerste uitkomst is het item geblokkeerd: geen token. Deblokkeren kan alleen met `deblokkeren=true` plus `deblokkeer_reden` (minstens 10 tekens); dit komt in het auditlog. Een blokkade zelf komt ook in het auditlog.

## Btw-bedrag 0 of ontbrekend: reden verplicht
Is het btw-bedrag 0 of ontbreekt het, dan geeft `yuki_boeking_voorstel` geen token zolang `btw_nul_reden` ontbreekt. Keuze: verlegd (medecontractant), intracommunautaire verwerving, vrijgesteld, buiten toepassingsgebied, kleine onderneming/vrijstellingsregeling, privé of niet-aftrekbaar, of ander (met verplichte `btw_nul_toelichting`). De reden komt tussen haakjes in de omschrijving van de relatieregel en in het auditlog.
Bij verlegd en intracommunautaire verwerving is de btw doorgaans zowel verschuldigd als aftrekbaar (verifieer actuele regel). De plugin boekt die btw niet zelf: de gebruiker bevestigt (`btw_regels_bevestigd=true`) en vult zo nodig aan met `btw_extra_regels` (rekening, bedrag, omschrijving; samen saldo 0,00; rekeningen worden tegen het rekeningschema gecontroleerd). Zonder bevestiging geen token.

## Dagboek en status 'Afgehandeld' (onderzocht 20/11/2026)
`Accounting.ProcessJournal` boekt altijd een **memoriaalpost**: `JournalType` kent enkel GeneralJournal, EndOfYearCorrection en FiscalCorrection (Journal.xsd). Er is geen veld voor het aankoop- of verkoopdagboek en geen koppeling aan een bestaand archiefdocument; een workflowdocument krijgt hierdoor niet de status 'Afgehandeld'. Gebruik ProcessJournal dus enkel voor echte memoriaalposten. Dit is afgedwongen: `yuki_boeking_voorstel` geeft voor een workflowdocument (aankoop of verkoop) geen token en `yuki_boeking_bevestigen` weigert zo'n voorstel, ook als het token op een andere manier is ontstaan, met een uitleg dat workflowdocumenten in de backoffice worden afgehandeld en dat een journaalpost een dubbele kost geeft
In de officiële API (api.yukiworks.be, WSDL's en XSD's) is **geen methode** gevonden die een bestaand workflowdocument tot aankoop- of verkoopfactuur verwerkt en afhandelt. Onderzocht: Purchase.ProcessPurchaseInvoices (schema https://api.yukiworks.be/schemas/PurchaseInvoices.xsd) en Sales.ProcessSalesInvoices / ProcessRecognizedSalesInvoices (https://api.yukiworks.be/schemas/SalesInvoices.xsd) maken een **nieuwe** factuur aan op basis van een meegestuurd document (DocumentBase64 en DocumentFileName verplicht, geen veld voor een bestaand document-ID); Archive kent enkel Upload*-methodes en leesmethodes; Backoffice enkel GetWorkflow en GetOutstandingQuestions (lezen). Afhandelen gebeurt in de Yuki-interface ('Afhandelen' of Backoffice status 'Afgehandeld').

## Afhandelen in de backoffice (leesfunctie)
Het afhandelen van een workflowdocument gebeurt in de Yuki-backoffice (knop 'Afhandelen'), niet via de API. Na afloop controleert `yuki_afhandeling_controle` (alleen lezen, `Backoffice.GetWorkflow`, https://api.yukiworks.be/ws/Backoffice.asmx?op=GetWorkflow) of het document niet meer in de workflow staat. Het antwoordformaat van GetWorkflow is niet gedocumenteerd: de controle zoekt het document-ID in alle waarden en meldt 'onbepaald' als er geen herkenbare ID-velden zijn. 'Niet meer in de workflow' is een sterke aanwijzing, geen bewijs, van 'Afgehandeld'.

## Bronnen (officieel)
- Yuki webservice Accounting, methode `ProcessJournal`: https://api.yukiworks.be/ws/Accounting.asmx?op=ProcessJournal
- Journaalschema (XSD): https://www.yukiworks.nl/schemas/Journal.xsd, namespace `urn:xmlns:http://www.theyukicompany.com:journal`. Samengevat: minstens twee `JournalEntry`, bedrag debet positief en credit negatief, som 0,00 (ook per datum), omschrijving maximaal 256 tekens, contact wordt aangemaakt als hij nog niet bestaat.

## Onzekerheden (eerlijk)
- **Niet live getest.** Er is geen enkele schrijfcall naar Yuki gedaan; alles is met mocks en synthetische [Voorbeeld]-data getest. Test eerst in een testadministratie met de dry-run.
- De XML wordt ongeëscaped in `xmlDoc` ingebed (zoals de XSD het voorschrijft); dat gedrag is niet live bevestigd.
- Yuki biedt geen gedocumenteerde methode voor "onverwerkte bankverrichtingen"; de wachtrekening is een benadering. Tegenboekingen worden alleen herkend op gelijk en tegengesteld bedrag.
- De velden van documentworkflow-rijen (ID, onderwerp, bedrag, relatie) zijn niet allemaal gedocumenteerd; ontbrekende velden vult de gebruiker aan via `aanpassingen`.
- Een journaalpost wordt niet automatisch gekoppeld aan het brondocument in het archief; `ProcessPurchaseInvoices` is niet gebruikt omdat die een nieuwe PDF-upload vraagt.
- De dubbelcontrole is een hulpmiddel en geen garantie: GetTransactionDetails geeft de relatie als naam (geen ContactId) en een documentreferentie; de vergelijking gebeurt op naam, bedrag, datum en referentie. Boekingen buiten het venster of op een andere rekening worden niet gezien.
- Een boeking kan niet via de plugin worden teruggedraaid: corrigeer in Yuki.
- Btw-tarieven, aftrekregels en fiscale aftrekbaarheid: verifieer actuele regel.

---

Powered by FISCALCI Accounting & Tax (Askin Alci)
