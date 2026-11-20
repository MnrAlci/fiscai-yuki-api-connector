# Hermes Agent (Nous Research)

**Wat het is.** [Hermes Agent](https://hermes-agent.nousresearch.com) is een open-source agent van Nous Research met native MCP-ondersteuning: stdioservers stelt u in `~/.hermes/config.yaml` in onder `mcp_servers` met `command`, `args` en `env` (officiële docs: <https://hermes-agent.nousresearch.com/docs/reference/mcp-config-reference>). Geheimen kunt u als `${NAAM}` refereren en bewaren in `~/.hermes/.env`.

**Is er een Yuki-specifieke "Hermes-plugin"?** Nee. FISCAi Yuki API Connector is een gewone MCP-stdioserver die Hermes Agent kan starten. Wij leveren geen aparte Hermes-plugin.

## Instellen

1. Installeer FISCAi Yuki API Connector (README) en noteer de absolute paden.
2. Zet `YUKI_ACCESS_KEY=...` in `~/.hermes/.env` (een privébestand op uw computer).
3. Voeg [`examples/hermes.config.yaml`](../../examples/hermes.config.yaml) samen met `~/.hermes/config.yaml`. Het bevat ook de optionele AgentMail-regel (`url` + `headers`); verwijder die als u AgentMail niet gebruikt.
4. Herstart Hermes Agent en vraag naar de lijst met tools. Beperk eventueel tools met het gedocumenteerde filter `tools: include/exclude`.

*verify current docs*: optienamen zoals `tools` of `timeout` veranderen per Hermes-versie; zie de referentie hierboven.

## Veiligheidsregels voor deze integratie

- Yuki blijft **alleen-lezen**: zet `YUKI_WRITE_ENABLED` niet aan.
- Er wordt niets automatisch verstuurd: de agent maakt een **concept**, u leest het en bevestigt elke verzending.
- De Yuki-sleutel en andere sleutels blijven op uw eigen computer, als omgevingsvariabele of in de geheimenopslag van het platform, nooit in een repository of in de chat.
- Geen klantgegevens naar derden (ook niet via mail- of agentdiensten) zonder toestemming van de klant.

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **België.** Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.
