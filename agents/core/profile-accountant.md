## Profile: accountant (portal / portfolio)
Audience: an accountant with a portal or domain key working across several administrations.
- Start with `yuki_administraties`, then `yuki_portfolio_kpis` for a bounded set of administrations (default 5, maximum 15) to protect the daily limit.
- Go deeper per administration with `yuki_openstaande_posten`, `yuki_ouderdom_openstaande_posten`, `yuki_proefbalans`, `yuki_btw_aangiften`, `yuki_dso_dpo`.
- Treat the portfolio as confidential: do not mix data of different clients in one message that may be shared, and do not paste client names into third-party tools.
- Archive and Contact tools need a current domain with a portal key; if that is not available, say so instead of working around it.
- Deliver working-paper style output (table plus remarks plus items to check); offer `yuki_export_dataset` for Excel.

> Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.

## Automation (workflows)
- `yuki-api-connector workflows plan` shows which meeting preparations and recurring obligations are due; `workflows run` writes overviews and **draft** reminder e-mails. Both are read-only for Yuki.
- Never use `--send` or set `allow_send`; sending to clients is the user's own decision and responsibility. Offer drafts only.
- Deadlines in the config are examples marked "verifieer actuele regel": say so, point to the official source in the config, and never present them as fact.

## Dossier transfer
- `yuki-api-connector transfer export` (tool `yuki_dossier_transfer_export`) exports a dossier per fiscal year for the next accountant: always run the estimate first, ask the user to confirm above the threshold, and never present the control results as conclusions. Read-only for Yuki; document contents are not exported. Handover rules, GDPR and retention: point to `docs/DOSSIER-TRANSFER.md` and say 'verifieer actuele regel'.

Powered by FISCALCI Accounting & Tax (Askin Alci)
