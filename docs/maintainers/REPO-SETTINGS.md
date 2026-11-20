# Recommended repository settings

Maintainer checklist for `fiscai-yuki-api-connector`. Items marked **API/ruleset file** can be imported; the rest are set by hand in the GitHub UI. UI labels change over time: verify against the current GitHub documentation.

> **Private repository.** GitHub does not enforce rulesets on private repositories of a free personal account (the Rulesets page shows a warning). Import them anyway so they are ready; they start to apply when the repository is public or the plan supports it. Verify current GitHub plan limits.

## 1. General
| Setting | Recommended value |
|---|---|
| Description | `Plugin for Grok Bot (also works with Copilot, Claude, Cursor, Windsurf and other MCP clients): read-only access to the Yuki accounting API for Belgian accountants and business owners. Powered by FISCALCI Accounting & Tax (Askin Alci)` (233 characters, limit 350) |
| Website | The documentation URL once Pages is live, otherwise empty |
| Topics | `mcp`, `mcp-server`, `model-context-protocol`, `yuki`, `visma`, `accounting`, `accountancy`, `bookkeeping`, `belgium`, `vat`, `grok-bot`, `ai-agents`, `copilot`, `claude`, `cursor`, `windsurf`, `python`, `read-only`, `power-bi`, `postman` |
| Visibility | Private until Askin decides to publish |
| Features | Issues on; Projects off; Wiki off; Discussions: optional (see section 6) |
| Pull requests | Allow squash merging only; auto-delete head branches on; always suggest updating PR branches |
| Social preview | Upload `docs/images/social-preview.png` (1280x640) under Settings, General, Social preview |

## 2. Rulesets (Settings, Rules, Rulesets, New ruleset, Import a ruleset)
- `.github/rulesets/main-protection.json`: no force push, no deletion, linear history, pull request required (0 approvals so a solo maintainer can merge their own PR; raise it when there are more maintainers; review threads must be resolved), required status checks from the CI workflow. The check names follow the job name and matrix (`test (3.10)` ... `test (3.13)`); verify the names after the first CI run and adjust.
- `.github/rulesets/release-tags.json`: tags matching `v*` cannot be deleted, moved or force-updated.
- Leave the bypass list empty, admin included. Every change to `main` goes through a pull request with green CI.

## 3. Actions (Settings, Actions, General)
- Actions permissions: allow actions created by GitHub and by verified creators only (the workflow only uses `actions/checkout` and `actions/setup-python`).
- Workflow permissions: **Read repository contents permission** (read-only `GITHUB_TOKEN`); do not allow Actions to create or approve pull requests.
- Fork pull request workflows: require approval for first-time contributors.

## 4. Security (Settings, Code security)
- Dependabot alerts: on. Dependabot security updates: on. Version updates come from `.github/dependabot.yml`.
- Secret scanning and push protection: on where available for your plan (verify availability for private repositories).
- Private vulnerability reporting: on (the SECURITY policy points to it).
- Code scanning (CodeQL): optional, free for public repositories; verify availability for private ones.

## 5. Labels
`.github/labels.yml` lists the label set. The labels were created through the GitHub connector; to sync them automatically you can add a label-sync action later.

## 6. Discussions
Optional. Leave off while the project is private and small; enable it when there are users asking questions, with categories Q&A, Ideas and Announcements, and point to it from the issue template config.

## 7. Documentation site (GitHub Pages)
Option A: Pages from the `/docs` folder of `main` (simple, works with the Markdown files). Option B: a docs workflow with MkDocs (`mkdocs-material`, MIT): build in CI and deploy with the official Pages actions, and set the Pages source to "GitHub Actions". Pages on private repositories needs a paid plan: verify current GitHub plans. Links that point outside `docs/` (for example `../README.md`) must be adjusted before publishing with MkDocs.

## 8. Environments
Create two environments (Settings, Environments): `pages` (created automatically when Pages deploys from Actions) and `release` (add yourself as required reviewer and restrict to the `main` branch and `v*` tags). No secrets are needed for this project; do not store the Yuki key in GitHub.

## 9. Releases
No release is made yet. When ready: update `CHANGELOG.md` and the version in `pyproject.toml`, `plugin.json`, `.cursor-plugin/plugin.json` and `yuki_mcp/__init__.py` (a test checks they match), tag `vX.Y.Z`, and publish a release from the tag.

## What was applied for you
Nothing in this file is applied automatically. Which items were applied through tooling is stated in the maintainer's hand-over report.

Powered by FISCALCI Accounting & Tax (Askin Alci)
