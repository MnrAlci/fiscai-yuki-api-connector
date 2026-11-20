# Roadmap

Plans, not promises. Order and scope can change. Read-only by default stays a hard rule.

## Next
- Tighten lint rules (unused imports and variables are currently ignored in `pyproject.toml`).
- Optional type hints and mypy for `export.py` and the analytics modules.
- More export datasets in the fixed export schema, with tests.
- Verify the client guides again against the vendors' current documentation.

## Later
- Retry also for transient HTTP 5xx responses (today: opt-in retry for network errors only).
- Containerised run documented end to end (a `Dockerfile` exists but is not yet part of CI).
- Signed releases and a changelog-driven release checklist.

## Not planned
- Sending email automatically. Drafts stay drafts.
- Writing to Yuki without the explicit write switch and per-entry confirmation.
