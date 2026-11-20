# Ready-made agent definitions

Agent definitions on top of the FISCAi Yuki API Connector MCP server. Nothing here installs or starts anything; copy the file for your platform.

> Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself.
>
> Powered by FISCALCI Accounting & Tax (Askin Alci)

Shared rules live in [core/instructions.md](core/instructions.md); two profiles: business owner (dashboard) and accountant (portal/portfolio). Everything is **read-only by default** and contains no keys.

| Platform | Files | Where to put them |
|---|---|---|
| Grok Bot (recommended) | `grok-bot/*.md` | paste into a Grok Bot agent after installing the plugin |
| Claude Code | `claude/claude-code/*.md` | `.claude/agents/` |
| Claude Desktop | `claude/claude-desktop/*.md` | project instructions |
| GitHub Copilot | `.github/agents/*.agent.md`, `github-copilot/copilot-instructions.md` | custom agents / `.github/copilot-instructions.md` |
| Cursor | `cursor/*.mdc` | `.cursor/rules/` |
| OpenAI Agents SDK | `openai-agents-sdk/agent.py` | run it yourself (Python example, stdio) |
| Open models (Ollama, LM Studio, others) | `generic/*.txt` | system prompt; the model and client must support MCP tool calling: verify current docs |

File formats follow each vendor's documentation as of 2026-11-20 (Claude Code subagents, GitHub Copilot custom agents, Cursor rules, OpenAI Agents SDK MCP stdio). Anything not confirmed is marked "verify current docs" in the file. The MCP server must be registered in your client first: see [docs/clients](../docs/clients/README.md).
