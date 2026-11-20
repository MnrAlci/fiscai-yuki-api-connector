# Dossieroverdracht per boekjaar

> Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

Draag een klantdossier over aan de volgende boekhouder (de confrater), georganiseerd **per boekjaar**, voor zover de Yuki-API dat toelaat. **Alleen lezen voor Yuki**; er worden enkel lokale bestanden geschreven.

## Wat u krijgt
```
out/
  README.md              voor de ontvangende boekhouder (formaten, beperkingen, professionele punten)
  2024/  2025/  ...      één map per boekjaar
    rekeningschema        rekeningschema
    proefbalans-slot / -begin / -jaarafsluiting   proefbalans op einde, begin en na afsluiting
    startbalans-api       beginsaldi zoals Yuki ze geeft
    grootboekmutaties     alle boekingslijnen, per rekening opgehaald (dagboeken/ enkel als Yuki een dagboekveld meegeeft)
    openstaande-debiteuren-einde / -crediteuren-einde   openstaande posten op de balansdatum
    contacten, btw-aangiften, btw-codes
    klasse-2-saldi-indicatie   saldi klasse 2 (indicatie, geen activaregister)
    archief-documenten-metadata   enkel met --include-documents (metadata, geen bestandsinhoud)
    MANIFEST.json         bestanden, aantal rijen, SHA-256
    CONTROL.md            afstemmingen
  2024.zip  2025.zip     met --zip
  .transfer-checkpoint.json   hervatstatus
```
Elke dataset wordt als CSV en JSON geschreven (en xlsx op aanvraag): `--format csv,json,xlsx`.

## Stap voor stap
1. **Bepaal de jaren.** De Yuki-API geeft geen lijst van boekjaren: u noemt ze (`--fiscal-year 2024 --fiscal-year 2025`) of gebruikt `--all-years [--first-year JJJJ]` (standaard: huidig jaar min 5). Gebroken boekjaar: `--fy-start-month 7` is een boekjaar dat in juli begint.
2. **Schat.** `yuki-api-connector transfer export --administration "[Voorbeeld] BV" --fiscal-year 2025 --out ./overdracht --estimate-only` toont een **bovengrens** van het aantal calls en het resterende dagquotum (ongeveer 1 à 2 calls).
3. **Bevestig.** Boven de drempel (`--threshold`, standaard 150 calls) of boven het resterende quotum vraagt de opdracht om `JA` te typen (of `--yes` in een script). Eronder start ze meteen. In een MCP-client geeft de tool `needs_confirmation`; de assistent moet u vragen en opnieuw aanroepen met `bevestig = true`.
4. **Uitvoeren.** `yuki-api-connector transfer export --administration "[Voorbeeld] BV" --fiscal-year 2024 --fiscal-year 2025 --out ./overdracht --zip`. Voeg `--include-documents` toe voor documentmetadata en `--all-accounts` om elke rekening op te halen (meer calls).
5. **Hervatten.** Bij het bereiken van het daglimiet stopt de run netjes (`status: onderbroken`). Voer **dezelfde opdracht** opnieuw uit (morgen): afgewerkte stappen worden overgeslagen. Een checkpoint van andere instellingen wordt geweigerd.
6. **Lees `CONTROL.md` per jaar.** Daarin: proefbalans som nul; beginbalans jaar N gelijk aan slotbalans jaar N-1 (enkel als N-1 in dezelfde map zit); begin plus mutaties gelijk aan slot per rekening; som van alle mutaties nul (enkel zinvol met `--all-accounts`); openstaande posten versus de saldi van rekeningen 40*/44* (indicatie). Een afwijking is een vraag voor de boekhouder, geen conclusie.
7. **Controleer de integriteit.** `MANIFEST.json` toont elk bestand met aantal rijen en SHA-256. Deel de checksums via een ander kanaal dan het pakket.
8. **Draag veilig over** (zie hieronder) en verwijder lokale kopieën die u niet meer nodig heeft.

## Beperkingen van de Yuki-API (verifieer actuele regel)
- Geen lijst van boekjaren; u geeft ze op.
- Boekingslijnen komen per rekening; de dagboekcode zit niet in de hier gelezen mutaties, dus een opdeling per dagboek bestaat enkel als Yuki zo'n veld meegeeft.
- Geen activaregister of afschrijvingstabel; saldi van klasse 2 zijn enkel een indicatie.
- Archief: alleen metadata. Bestandsinhoud is niet beschikbaar via de toegelaten leesmethodes; exporteer de documenten uit Yuki zelf.
- Het daglimiet voor calls geldt (deze plugin staat standaard op 900 per domein per dag; zie `yuki_status`). Verifieer de actuele Yuki-regels.
- De grenzen van het boekjaar volgen `--fy-start-month`; de eigen jaardefinities van Yuki worden niet gelezen.
- De standaardmodus haalt mutaties enkel op voor rekeningen met een saldo of beweging aan begin of einde van het jaar; rekeningen die op nul uitkomen worden overgeslagen tenzij `--all-accounts`.

## Professionele en wettelijke punten (verifieer de actuele regels; dit is geen juridisch advies)
- **Overdracht en deontologie**: volg de regels van uw beroepsinstituut voor de overdracht van een dossier aan een collega (bv. ITAA <https://www.itaa.be> of IBR/IRE <https://www.ibr-ire.be>, naargelang uw titel) en de communicatie met de nieuwe boekhouder. Verifieer de actuele regels bij uw instituut.
- **Klant**: de klant moet op de hoogte zijn van en akkoord gaan met de overdracht; zorg voor een rechtsgrond.
- **GDPR**: het pakket bevat persoonsgegevens (contacten, mogelijk documenten). Beperk de toegang, bewaar het versleuteld, verwijder kopieën die u niet meer nodig heeft. Gegevensbeschermingsautoriteit: <https://www.gegevensbeschermingsautoriteit.be>.
- **Veilig overmaken**: gebruik een versleutelde zip of een beveiligd platform; stuur het wachtwoord via een ander kanaal.
- **Bewaartermijnen**: wettelijke bewaartermijnen blijven ook na de overdracht voor u gelden; verifieer de actuele regel bij de FOD Economie of de FOD Financiën <https://financien.belgium.be/nl>.

## Tool, CLI en hooks
- MCP-tool: `yuki_dossier_transfer_export` (argumenten: `administratie`, `jaren` of `alle_jaren`, `export_map`, `zip`, `inclusief_documenten`, `alle_rekeningen`, `formaten`, `alleen_schatting`, `bevestig`, `drempel`, `hervat`).
- CLI: `yuki-api-connector transfer export ...` (`--dry-run` toont het plan zonder calls). Exitcode 6 betekent dat de bevestiging ontbrak.
- Hooks: elke Yuki-call loopt via `pre_call`/`post_call`/`on_error`; `on_export` volgt bij een voltooide of onderbroken run ([HOOKS.nl.md](HOOKS.nl.md)).

Powered by FISCALCI Accounting & Tax (Askin Alci)
