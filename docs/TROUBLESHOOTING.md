# Troubleshooting and FAQ

> Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.

## The client does not show any Yuki tools
1. Check that the server starts: `make run` (or `python3 server/run_server.py`) should wait silently for input. Stop it with Ctrl+C.
2. Check the path to the Python in your virtual environment in the client config (absolute path).
3. Restart the client fully after changing its MCP configuration.
4. Look at the client's own MCP log. Each client has one; see the client guide in `docs/clients/`.

## "YUKI_ACCESS_KEY" is missing or rejected
- The key must be available to the process: as an environment variable in your shell, or via the client's secure variable mechanism. Never paste it in a chat.
- Create or check the key in Yuki (rights are per service group; you need the Directie or Portaalbeheerder role). Exact menu labels: verify in your own Yuki or the official Yuki help.
- A portal key lists all administrations; a domain key only one.

## "Daily limit reached"
The safety limit (default 900 calls per domain per day) protects your quota. Wait until tomorrow (Europe/Brussels), or ask for fewer, narrower queries; cached answers do not count again.

## I get an administration-not-found or ambiguous error
Use the exact administration name or its id from `yuki_list_administrations`.

## Is anything written to Yuki?
No, by default. Writing is off unless you set the explicit write switch and confirm each entry. See the README and `docs/BOEKINGSWORKFLOW.md`.

## Where is my data stored?
In the data folder (`YUKI_DATA_DIR`, default `~/.fiscai-yuki-api-connector`): encrypted cache, daily counter and audit log, mode 0600. See [PRIVACY-DATA-FLOW.md](PRIVACY-DATA-FLOW.md).

## Parquet export fails
Parquet needs the optional `pyarrow` package: `pip install pyarrow`. CSV, JSON and xlsx need nothing extra.

## Tests fail on my machine
Run `make install` then `make test`. The tests use synthetic `[Voorbeeld]` data and make no network calls.

Powered by FISCALCI Accounting & Tax (Askin Alci)
