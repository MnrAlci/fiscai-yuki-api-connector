# Tools (70)

All tools are read-only unless the optional booking workflow is on (see [BOEKINGSWORKFLOW.md](BOEKINGSWORKFLOW.md)). Tool descriptions are in Dutch.

| Tool | Beschrijving |
|---|---|
| `yuki_status` | Yuki-status en daglimiet: Dagteller per domein, ingestelde daglimiet (standaard 900), toegangsniveau en antwoordcache. |
| `yuki_administraties` | Administraties: Alle administraties die met de sleutel bereikbaar zijn. |
| `yuki_proefbalans` | Proef- en saldibalans: Saldo per grootboekrekening op een datum (Accounting.GLAccountBalance[Fiscal|YearEnd]). |
| `yuki_netto_omzet` | Netto-omzet: Netto-omzet in een periode (Accounting.NetRevenue[Fiscal]). |
| `yuki_openstaande_posten` | Openstaande posten: Openstaande debiteuren of crediteuren, optioneel op een peildatum (Accounting.Outstanding{Debtor|Creditor}Items[ByDateOutstanding]). |
| `yuki_grootboekmutaties` | Grootboekmutaties: Boekingen op één grootboekrekening (AccountingInfo.GetTransactionDetails). |
| `yuki_rekeningschema` | Rekeningschema: Alle grootboekrekeningen (AccountingInfo.GetGLAccountScheme). |
| `yuki_boekjaar_gewijzigd` | Boekjaar laatst gewijzigd: Laatste wijzigingsdatum van de boekingen in een boekjaar (AccountingInfo.GetFinancialYearModifiedDate). |
| `yuki_jaartotalen` | Jaartotalen en ratio's: Jaartotalen (MAR) en ratio's uit proef- en saldibalans en netto-omzet. |
| `yuki_ouderdom_openstaande_posten` | Ouderdomsanalyse openstaande posten: Ouderdom (niet vervallen, 0-30, 31-60, 61-90, >90 dagen) van openstaande debiteuren/crediteuren; negatieve open bedragen apart (neutraal gelabeld, type enkel indien Yuki het meegeeft). |
| `yuki_dso_dpo` | DSO en DPO: Gemiddelde betaaltermijn: DSO = debiteuren/omzet x dagen, DPO = crediteuren/inkopen (klasse 60) x dagen, vanaf 1 januari. |
| `yuki_top_relaties` | Top debiteuren of crediteuren: Grootste openstaande saldi per relatie. |
| `yuki_periodevergelijking` | Periodevergelijking: Omzet, kosten en resultaat voor een maand, kwartaal of jaar, vergeleken met de vorige periode en/of hetzelfde van vorig jaar. |
| `yuki_marge_kostenstructuur` | Marge en kostenstructuur: Brutomarge, nettomarge en kosten per MAR-klasse (60-68) in een periode. |
| `yuki_liquiditeit` | Liquiditeitsratio's: Current ratio, cash ratio, werkkapitaal, solvabiliteit op een datum. |
| `yuki_uitschieters` | Uitschieters in het grootboek: Statistische uitschieters (mediaan/MAD) en mogelijk dubbele boekingen op één grootboekrekening. |
| `yuki_dashboard` | Dashboard: Dashboard met omzet, kosten, resultaat, liquiditeit, openstaande debiteuren/crediteuren met ouderdom en btw-saldo-indicatie. |
| `yuki_export_dataset` | Export naar CSV, Excel, JSON of Parquet: Schrijft een dataset met vast, gedocumenteerd schema (kpis, saldi, openstaande_posten) als lokaal bestand in een map naar keuze, voor Power BI, Qlik, Tableau, Metabase, Excel enz. |
| `yuki_dossier_transfer_export` | Dossieroverdracht per boekjaar (export voor de volgende boekhouder): Exporteert per boekjaar naar een map: rekeningschema, proefbalans (slot, begin, jaarafsluiting), startbalans, grootboekmutaties, openstaande posten op balansdatum, contacten, btw-gegevens, klasse-2-saldi (indicatie) en optioneel documentmetadata; met MANIFEST.json (SHA-256), CONTROL.md (afstemmingen) en README voor de ontvanger. |
| `yuki_dashboard_kpis` | Kerncijfers (compact, ondernemer): Compacte kerncijfers van één administratie voor een eigen dashboard: omzet, kosten, resultaat, marge, liquide middelen, liquiditeit, open debiteuren en crediteuren (totaal en vervallen), DSO/DPO, btw-saldo-indicatie en optioneel de vergelijking met de vorige periode. |
| `yuki_portfolio_kpis` | Kerncijfers per administratie (portfolio, accountant): Kerncijfers per administratie over meerdere dossiers heen (omzet, kosten, resultaat, liquide middelen, open debiteuren en crediteuren) voor een portfolio-overzicht. |
| `yuki_herinneringsmail` | Herinneringsmail (concept): Bouwt een CONCEPTmail voor één relatie met openstaande posten. |
| `yuki_handleiding_saldi` | Handleiding saldi: Uitleg over positieve en negatieve saldi bij debiteuren en crediteuren en wat te doen. |
| `yuki_afpuntingsvoorstellen` | Afpuntingsvoorstellen: Zoekt voorstellen om negatieve open posten (meestal betalingen zonder gekoppelde factuur) af te punten: 1-op-1 (gelijk bedrag of binnen tolerantie), meerdere betalingen voor één factuur, één betaling voor meerdere facturen en lagere-zekerheidsvoorstellen over verschillende of gelijkaardige relaties heen (o.a. |
| `yuki_opslag_status` | Opslaglocatie: status: Toont welke opslaglocatie de gebruiker koos voor het permanente dossier (per administratie) en welke koppeling daarvoor nodig is. |
| `yuki_opslag_instellen` | Opslaglocatie: instellen: Bewaart de keuze van de gebruiker voor het permanente dossier in de lokale configuratie (per administratie, of voor alle administraties als de gebruiker dat uitdrukkelijk vraagt met administratie='*'). |
| `yuki_boeking_voorstel` | Boeking: volgend item en voorstel: Toont het volgende onbehandelde item (document uit de documentworkflow of bankverrichting op de wachtrekening) met een boekingsvoorstel (rekening, btw-code, relatie, bedrag, omschrijving; Belgisch MAR en btw-stelsel). |
| `yuki_boeking_overslaan` | Boeking: item overslaan: Markeert een item lokaal als overgeslagen zodat het niet meer als volgend item verschijnt. |
| `yuki_boeking_bevestigen` | Boeking: bevestigen (schrijft in Yuki): SCHRIJFT één journaalpost in Yuki (Accounting.ProcessJournal) na uitdrukkelijke bevestiging van de gebruiker voor precies dit voorstel. |
| `yuki_afhandeling_controle` | Controle na afhandelen in de backoffice: Leest Backoffice.GetWorkflow en controleert of een document (document_id uit het boekingsvoorstel, 'D:<id>') niet meer in de workflow staat, nadat het in de Yuki-backoffice is afgehandeld. |
| `yuki_boeking_status` | Boeking: status: Toont of de boekingsworkflow aanstaat, de vervaltijd van tokens, het dagmaximum en het aantal boekingen vandaag. |
| `yuki_openstaande_posten_periode` | Openstaande posten per periode: Openstaande debiteuren- of crediteurenposten met factuurdatum tussen twee data; optioneel met betaalreferentie. |
| `yuki_grootboektransacties` | Grootboektransacties (Accounting): Transacties van één grootboekrekening in een periode (oudere Accounting-variant; zie ook yuki_grootboekmutaties). |
| `yuki_controleer_open_post` | Controleer openstaande post: Open bedrag van één transactie via factuurnummer of ID (GUID). |
| `yuki_domeinen` | Domeinen: Alle domeinen die met deze sleutel bereikbaar zijn. |
| `yuki_bedrijven` | Bedrijven: Alle beschikbare administraties (Companies). |
| `yuki_huidig_domein` | Huidig domein: Het huidige Yuki-domein van de sessie. |
| `yuki_administratie_id` | Administratie-ID opzoeken: Administratie-ID (GUID) bij een exacte administratienaam. |
| `yuki_startbalans` | Startbalans per rekening: Beginsaldo's per grootboekrekening voor een boekjaar. |
| `yuki_periodetabel` | Startdatum boekjaar: Startdatum van een boekjaar per administratie. |
| `yuki_transacties_gepagineerd` | Transacties (gepagineerd): Grootboektransacties met paginering; haalt standaard alle pagina's op (max_paginas begrenst). |
| `yuki_aangepaste_betaalmethodes` | Aangepaste betaalmethodes: Alle aangepaste betaalmethodes. |
| `yuki_rgs_schema` | RGS-rekeningschema: Rekeningschema met RGS-codes (Nederlandse referentie; in België meestal niet gebruikt). |
| `yuki_projecten` | Projecten: Projecten (GetProjects of GetProjectsAndID). |
| `yuki_projectsaldo` | Projectsaldo: Saldo van een project per grootboekrekening. |
| `yuki_contact_standaardwaarden` | Standaardwaarden contact: Standaardwaarden van een contact in een administratie. |
| `yuki_verkoopitems` | Verkoopartikelen: Verkoopartikelen van een administratie. |
| `yuki_btw_aangiftes` | Btw-aangiften: Lijst van btw-aangiften voor een jaar (lezen, geen indiening). |
| `yuki_btw_codes` | Actieve btw-codes: Actieve btw-codes van een administratie. |
| `yuki_backoffice_workflow` | Backoffice-workflow: De workflow (te verwerken documenten) van een administratie (lezen). |
| `yuki_archief_mappen` | Archiefmappen: Alle archiefmappen. |
| `yuki_archief_mappen_aantallen` | Aantal documenten per map: Aantallen per map voor een jaar. |
| `yuki_archief_tabs` | Tabs van een map: Tabs van een archiefmap. |
| `yuki_archief_documenten` | Documenten (alle): Documentmetadata, gepagineerd (alleen metadata, geen bestandsinhoud). |
| `yuki_archief_documenten_in_map` | Documenten in map: Documentmetadata in een map. |
| `yuki_archief_documenten_in_tab` | Documenten in tab: Documentmetadata in een tab. |
| `yuki_archief_documenten_per_type` | Documenten per type: Documentmetadata per documenttype. |
| `yuki_archief_gewijzigd_per_type` | Gewijzigde documenten per type: Sinds een datum gewijzigd. |
| `yuki_archief_gewijzigd_in_map` | Gewijzigde documenten in map: Sinds een datum gewijzigd. |
| `yuki_archief_zoeken` | Documenten zoeken: Zoeken in documentmetadata. |
| `yuki_archief_document` | Document zoeken op ID: Metadata van één document. |
| `yuki_archief_document_xml` | Document XML-gegevens: Herkende gegevens (XML) van een document, geen bestand. |
| `yuki_archief_document_paginas` | Aantal pagina's van een document: Aantal pagina-afbeeldingen. |
| `yuki_archief_betaalmethodes` | Betaalmethodes (archief): Betaalmethodes. |
| `yuki_archief_kostencategorieen` | Kostencategorieën: Kostencategorieën. |
| `yuki_archief_valuta` | Valuta's: Valuta's. |
| `yuki_archief_menu` | Menu: Menustructuur van het archief. |
| `yuki_archief_projecten` | Projecten (archief): Projecten van een administratie. |
| `yuki_contacten_zoeken` | Contacten zoeken: Contacten zoeken; gepagineerd. |
| `yuki_klanten_leveranciers` | Klanten en leveranciers: Klanten en/of leveranciers; gepagineerd. |

---

Powered by FISCALCI Accounting & Tax (Askin Alci)
