# Any other MCP client

FISCAi Yuki API Connector is a standard MCP server over **stdio** (JSON-RPC). Any client that can start a local command can use it.

| Setting | Value |
|---|---|
| Transport | stdio |
| Command | `/ABSOLUTE/PATH/TO/fiscai-yuki-api-connector/.venv/bin/python` |
| Arguments | `/ABSOLUTE/PATH/TO/fiscai-yuki-api-connector/server/run_server.py` |
| Environment | `YUKI_ACCESS_KEY` (secret), `YUKI_ACCESS_LEVEL` = `domein` or `portaal` |

Most clients use the `mcpServers` JSON shape in [`examples/generic-mcp-stdio.json`](../../examples/generic-mcp-stdio.json). If your client supports environment references, use them for the key; otherwise keep the file private. Check your client's current documentation (verify current client docs).

Optional console entry point: after `pip install .` the command `yuki-api-connector` starts the same server (see `pyproject.toml`).

Config format checked against the client's official documentation on 2026-11-20. Not tested live in the client by the author; if something differs, follow the client's current documentation (verify current client docs).

Back to [all clients](README.md)

---

Powered by FISCALCI Accounting & Tax (Askin Alci)

> **Belgium.** Made for Belgian accountants and bookkeepers: it follows the Belgian chart of accounts (MAR) and Belgian VAT. Outside Belgium, check the local rules yourself.
