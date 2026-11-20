# OpenClaw

**Wat het is.** [OpenClaw](https://docs.openclaw.ai) is een agent-gateway met een beheerd MCP-register. Servers staan onder `mcp.servers` in de config (`~/.openclaw/openclaw.json`); stdio-items gebruiken `command`, `args` en `env`. U beheert ze ook met de `openclaw mcp`-commando's (`add`, `list`, `doctor --probe`) of in de Control UI (officiële docs: <https://docs.openclaw.ai/tools/mcp>, <https://docs.openclaw.ai/gateway/config-extensions>).

**Is er een Yuki-specifieke "OpenClaw-plugin"?** Nee. OpenClaw start FISCAi Yuki API Connector als gewone MCP-stdioserver. Wij leveren geen aparte OpenClaw-plugin.

## Instellen

1. Installeer FISCAi Yuki API Connector (README) en noteer de absolute paden.
2. Voeg de server uit [`examples/openclaw.mcp.json`](../../examples/openclaw.mcp.json) toe aan `mcp.servers` (of gebruik `openclaw mcp add`). Het voorbeeld bevat ook een optionele AgentMail-brug; verwijder die als u ze niet gebruikt.
3. Geef `YUKI_ACCESS_KEY` mee via het ondersteunde geheimenmechanisme van OpenClaw of de omgeving van de gateway. De docs raden af om sleutels als letterlijke waarde in de config te zetten; of `${VAR}` in `env` wordt ingevuld hangt van uw versie af (*verify current docs*).
4. Draai `openclaw mcp doctor fiscai-yuki-api-connector --probe` om de verbinding te controleren.

OpenClaw laat om veiligheidsredenen sommige loader-/interpretervariabelen uit de stdio-`env` weg; `YUKI_*`-variabelen zijn gewoon en worden niet geraakt.

## Veiligheidsregels voor deze integratie

- Yuki blijft **alleen-lezen**: zet `YUKI_WRITE_ENABLED` niet aan.
- Er wordt niets automatisch verstuurd: de agent maakt een **concept**, u leest het en bevestigt elke verzending.
- De Yuki-sleutel en andere sleutels blijven op uw eigen computer, als omgevingsvariabele of in de geheimenopslag van het platform, nooit in een repository of in de chat.
- Geen klantgegevens naar derden (ook niet via mail- of agentdiensten) zonder toestemming van de klant.

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **België.** Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.
