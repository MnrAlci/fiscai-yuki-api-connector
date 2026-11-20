# Dossier transfer per fiscal year

> Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

Hand a client file over to the next accountant (the *confrère*), organised **per fiscal year**, as far as the Yuki API allows. It is **read-only for Yuki**; it only writes local files.

## What you get
```
out/
  README.md              for the receiving accountant (formats, limits, professional points)
  2024/  2025/  ...      one folder per fiscal year
    rekeningschema        chart of accounts
    proefbalans-slot / -begin / -jaarafsluiting   trial balances at year end, year start and after closing
    startbalans-api       opening balances as Yuki returns them
    grootboekmutaties     all entries, fetched per account (dagboeken/ only if Yuki returns a journal field)
    openstaande-debiteuren-einde / -crediteuren-einde   open items at the balance date
    contacten, btw-aangiften, btw-codes
    klasse-2-saldi-indicatie   class 2 balances (indication, not a fixed-asset register)
    archief-documenten-metadata   only with --include-documents (metadata, no file contents)
    MANIFEST.json         files, row counts, SHA-256
    CONTROL.md            reconciliations
  2024.zip  2025.zip     with --zip
  .transfer-checkpoint.json   resume state
```
Each dataset is written as CSV and JSON (and xlsx on request): `--format csv,json,xlsx`.

## Step by step
1. **Decide the years.** The Yuki API gives no list of fiscal years: you name them (`--fiscal-year 2024 --fiscal-year 2025`) or use `--all-years [--first-year YYYY]` (default: current year minus 5). Broken fiscal years: `--fy-start-month 7` means a year that starts in July.
2. **Estimate.** `yuki-api-connector transfer export --administration "[Voorbeeld] BV" --fiscal-year 2025 --out ./overdracht --estimate-only` prints an **upper bound** of the calls and the remaining daily quota (about 1 to 2 calls).
3. **Confirm.** Above the threshold (`--threshold`, default 150 calls) or above the remaining quota, the command asks you to type `JA` (or pass `--yes` in a script). Below it, it runs directly. In an MCP client the tool returns `needs_confirmation`; the assistant must ask you and call again with `bevestig = true`.
4. **Run.** `yuki-api-connector transfer export --administration "[Voorbeeld] BV" --fiscal-year 2024 --fiscal-year 2025 --out ./overdracht --zip`. Add `--include-documents` for document metadata and `--all-accounts` to fetch every account (more calls).
5. **Resume.** If the daily limit is reached the run stops cleanly (`status: onderbroken`). Run the **same command** again (tomorrow or after raising your own limit within the plugin rules): finished steps are skipped. A checkpoint from other settings is refused.
6. **Check `CONTROL.md` per year.** It shows: trial balance sums to zero; opening balance year N equals the closing balance of year N-1 (only when N-1 is in the same folder); opening plus entries equals closing per account; sum of all entries is zero (only meaningful with `--all-accounts`); open items versus the 40*/44* account balances (indication). A deviation is a question for the accountant, not a conclusion.
7. **Verify integrity.** `MANIFEST.json` lists every file with its row count and SHA-256. Share the checksums through another channel than the package.
8. **Hand over securely** (see below) and delete local copies you no longer need.

## Yuki API limits (verifieer actuele regel)
- No list of fiscal years; you provide them.
- Ledger entries come per account; the journal (*dagboek*) code is not part of the entries read here, so a split per journal exists only if Yuki returns such a field.
- No fixed-asset register or depreciation schedule; class 2 balances are an indication only.
- Archive: metadata only. File contents are not available through the read-only allow-list; export the documents from Yuki itself.
- The daily call limit applies (this plugin defaults to 900 per domain per day; see `yuki_status`). Verify the current Yuki rules.
- Fiscal-year boundaries follow `--fy-start-month`; Yuki's own year definitions are not read.
- Default mode fetches entries only for accounts with a non-zero balance or movement at the start or end of the year; accounts that net to zero are skipped unless `--all-accounts`.

## Professional and legal points (verify the current rules; this is not legal advice)
- **Handover and ethics**: follow the rules of your professional institute for transferring a file to a colleague (for example ITAA <https://www.itaa.be> or IBR/IRE <https://www.ibr-ire.be>, depending on your title) and the communication with the incoming accountant. Verify the current rules with your institute.
- **Client**: the client must know about and agree to the transfer; make sure you have a legal basis.
- **GDPR**: the package contains personal data (contacts, possibly documents). Limit access, store it encrypted, delete copies you no longer need. Belgian Data Protection Authority: <https://www.gegevensbeschermingsautoriteit.be>.
- **Secure transfer**: use an encrypted zip or a secure platform; send the password through a different channel.
- **Retention**: statutory retention periods still apply to you after the handover; verify the current rule with the FOD Economie or FOD Financiën <https://financien.belgium.be/nl>.

## Tool, CLI and hooks
- MCP tool: `yuki_dossier_transfer_export` (arguments: `administratie`, `jaren` or `alle_jaren`, `export_map`, `zip`, `inclusief_documenten`, `alle_rekeningen`, `formaten`, `alleen_schatting`, `bevestig`, `drempel`, `hervat`).
- CLI: `yuki-api-connector transfer export ...` (`--dry-run` shows the plan without calls). Exit code 6 means confirmation was missing.
- Hooks: every Yuki call goes through `pre_call`/`post_call`/`on_error`; `on_export` fires when a run completes or is interrupted ([HOOKS.md](HOOKS.md)).

Powered by FISCALCI Accounting & Tax (Askin Alci)
