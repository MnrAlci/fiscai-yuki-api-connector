# AgentMail

**Wat het is.** [AgentMail](https://www.agentmail.to) is een e-maildienst voor AI-agents: agents krijgen eigen mailboxen en kunnen via een API mail lezen, opstellen en versturen. Er is een officiële MCP-server op `https://mcp.agentmail.to/mcp` en een npm/PyPI-stdiobrug `agentmail-mcp` voor clients die enkel stdio kennen (docs: <https://docs.agentmail.to/integrations/mcp>).

**Wat deze integratie is.** AgentMail koppelt niet rechtstreeks aan FISCAi Yuki API Connector; u draait **beide MCP-servers naast elkaar** in dezelfde client. FISCAi Yuki API Connector leest de cijfers lokaal, AgentMail levert de mailbox. Er zit geen code van ons die met AgentMail praat. Controleer zelf de actuele prijzen en voorwaarden van AgentMail; een account en sleutel aanmaken is uw eigen keuze (verify current docs).

## Instellen

1. Installeer eerst FISCAi Yuki API Connector in uw client (zie [clientgidsen](../clients/README.md)).
2. Maak een AgentMail-API-sleutel in de console (Settings, API Keys, volgens de docs van AgentMail) en bewaar hem in de omgevingsvariabele `AGENTMAIL_API_KEY`.
3. Voeg AgentMail toe als tweede server.
   - Remote (voorkeur als de client headers ondersteunt): [`examples/agentmail-hosted.mcp.json`](../../examples/agentmail-hosted.mcp.json) (header `x-api-key` uit `${env:AGENTMAIL_API_KEY}`). Clients met OAuth (bv. Claude) kunnen de kale URL zonder sleutel gebruiken.
   - stdiobrug: [`examples/agentmail-stdio.mcp.json`](../../examples/agentmail-stdio.mcp.json) (`npx -y agentmail-mcp`, Node.js 20+). Met `--tools` beperkt u de tools (controleer eerst de echte toolnamen in uw client).
4. Herstart de client en controleer dat beide servers hun tools tonen.

## Voorbeeldscenario: periodieke KPI-mail (ondernemer)

1. U vraagt: "Lees mijn kerncijfers van deze maand met `yuki_dashboard_kpis` en schrijf een korte samenvatting."
2. De agent leest Yuki lokaal (alleen-lezen) en schrijft een gewone samenvatting.
3. De agent maakt een **AgentMail-concept** gericht aan **uw eigen** adres.
4. U leest het concept. Pas als u "verstuur" zegt, verstuurt de agent het. Een planning (als uw platform die heeft) mag het concept *voorbereiden*, nooit versturen zonder uw bevestiging.

## Voorbeeldscenario: dossieroverzicht (accountant)

Zelfde verloop met `yuki_portfolio_kpis`, maar enkel voor dossiers waarvoor de klant akkoord is dat cijfers gemaild worden. Verstuur bij voorkeur naar uzelf of naar het eigen adres van de klant en houd de samenvatting kort. De mail loopt via de servers van AgentMail: dat is een derde partij.

## Veiligheidsregels voor deze integratie

- Yuki blijft **alleen-lezen**: zet `YUKI_WRITE_ENABLED` niet aan.
- Er wordt niets automatisch verstuurd: de agent maakt een **concept**, u leest het en bevestigt elke verzending.
- De Yuki-sleutel en andere sleutels blijven op uw eigen computer, als omgevingsvariabele of in de geheimenopslag van het platform, nooit in een repository of in de chat.
- Geen klantgegevens naar derden (ook niet via mail- of agentdiensten) zonder toestemming van de klant.
- Mail via AgentMail verlaat uw computer. Mail enkel wat u ook via een andere externe maildienst zou versturen.

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **België.** Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.
