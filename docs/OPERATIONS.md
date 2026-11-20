# Errors, logging, timeouts and limits

How the connector behaves when things go wrong. Behaviour described here matches the code; where a feature does not exist it says so.

## Errors
- Every tool call returns a normal MCP result. On failure the result has `isError: true` and a short, human-readable message. Messages are scrubbed of secrets before they leave the server.
- Typical error classes: configuration missing (`YUKI_ACCESS_KEY` not set), a SOAP fault from Yuki, an ambiguous or unknown administration, and the daily call limit reached.
- Tool arguments are validated; unknown methods and all write methods are refused by an allow-list (the only exception is the optional booking workflow, off by default).

## Logging policy
- The server speaks JSON-RPC on stdout. It does **not** write a general log file. Start-up failures go to stderr as one short line.
- Secrets (keys, tokens, session ids) are never written to stdout, stderr, the cache index or the audit log. Output passes through a scrubber (`scrub`) before it is returned or stored.
- The optional booking workflow keeps a local audit log (JSON lines, file mode 0600) in the data folder; it holds timestamps, tool and reference, not keys.
- Do not paste raw logs into public issues without checking them. Use synthetic data in bug reports.

## Timeouts
- Each Yuki HTTP request has a 60 second timeout (set in the SOAP client). The optional local HTTP endpoint of `serve --http` is localhost-only.

## Retries
- Automatic retry is **opt-in** and off by default: set `YUKI_MAX_RETRIES` (1 to 5) to retry *network errors only* with exponential backoff and jitter. Yuki faults and write calls are never retried. Otherwise a failed call is reported as an error and you can try again.

## Rate limit and cache
- A hard daily limit protects your Yuki quota: default 900 calls per administration domain per day, warning at 720. A call over the limit is refused with a clear message; there is no silent bypass.
- Responses are cached locally for a short time; see the environment variables table in the README. Cache entries are not shared and live in the data folder (`YUKI_DATA_DIR`).

## What to include in a bug report
Version (`pyproject.toml`), Python version, client name and version, the tool name, the error message (secrets removed), and steps to reproduce with `[Voorbeeld]` data.

Powered by FISCALCI Accounting & Tax (Askin Alci)
