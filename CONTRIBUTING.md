# Contributing

Thanks for your interest. This is a small, safety-first project: it must never write to Yuki unless the booking workflow is explicitly enabled.

## Ground rules
- **No real data.** Tests, fixtures, docs and screenshots use synthetic `[Voorbeeld]` data only. Never commit keys, `.env` files, logs, Yuki figures or client data.
- **Read-only first.** Do not add write methods to the allow-list. Changes to `boeking.py`, `transport.py` or the safety layer need tests that prove the guard still holds.
- **Keep the attribution.** `Powered by FISCALCI Accounting & Tax (Askin Alci)` must stay unchanged (see `NOTICE`); the code checks it.
- **Belgian scope.** Accounting rules follow the Belgian MAR and VAT; say so when you add rules.

## Development
```bash
python3 -m venv .venv && .venv/bin/pip install -r requirements.txt pytest
PYTHONDONTWRITEBYTECODE=1 .venv/bin/python -m pytest -p no:cacheprovider -q tests
```
All tests use mocks; no Yuki call is made.

## Pull requests
Open an issue first for larger changes. Describe what changes and add tests. By contributing you agree that your contribution is licensed under Apache-2.0.
