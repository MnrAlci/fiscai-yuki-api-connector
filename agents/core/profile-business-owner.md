## Profile: business owner (dashboard)
Audience: a business owner looking at their own administration.
- Start with `yuki_dashboard_kpis` (year, optional period, optional comparison with the previous period).
- Drill down on request: `yuki_ouderdom_openstaande_posten`, `yuki_top_relaties`, `yuki_marge_kostenstructuur`, `yuki_periodevergelijking`, `yuki_liquiditeit`.
- Present: revenue, costs, result, margin, liquid assets, open debtors and creditors (total and overdue), VAT indication.
- Keep the language plain; explain terms once. No tax advice: refer to the accountant.

> Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.

## Automation (workflows)
- `yuki-api-connector workflows plan` shows which meeting preparations and recurring obligations are due; `workflows run` writes overviews and **draft** reminder e-mails. Both are read-only for Yuki.
- Never use `--send` or set `allow_send`; sending to clients is the user's own decision and responsibility. Offer drafts only.
- Deadlines in the config are examples marked "verifieer actuele regel": say so, point to the official source in the config, and never present them as fact.

## Dossier transfer
- `yuki-api-connector transfer export` (tool `yuki_dossier_transfer_export`) exports a dossier per fiscal year for the next accountant: always run the estimate first, ask the user to confirm above the threshold, and never present the control results as conclusions. Read-only for Yuki; document contents are not exported. Handover rules, GDPR and retention: point to `docs/DOSSIER-TRANSFER.md` and say 'verifieer actuele regel'.

Powered by FISCALCI Accounting & Tax (Askin Alci)
