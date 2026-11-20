"""OpenAI Agents SDK example: the MCP server over stdio. Verify current docs: https://openai.github.io/openai-agents-python/mcp/

Install (in your own environment; this repository does not install anything for you):
    pip install openai-agents
Set OPENAI_API_KEY and YUKI_ACCESS_KEY in your shell (never in this file). Read-only: YUKI_WRITE_ENABLED is deliberately not set.
Usage: python agent.py "Give me a dashboard of administration [Voorbeeld] BV for 2026"
Note: data returned by the tools is sent to the model provider you choose (see docs/PRIVACY-DATA-FLOW.md).
Powered by FISCALCI Accounting & Tax (Askin Alci)
"""
import asyncio
import os
import sys
from pathlib import Path

from agents import Agent, Runner
from agents.mcp import MCPServerStdio

ROOT = Path(__file__).resolve().parents[2]
INSTRUCTIONS = (ROOT / "agents" / "core" / "instructions.md").read_text(encoding="utf-8") + "\n" + (
    ROOT / "agents" / "core" / "profile-business-owner.md").read_text(encoding="utf-8")  # or profile-accountant.md


async def main(question: str) -> None:
    env = {k: os.environ[k] for k in ("YUKI_ACCESS_KEY", "PATH") if k in os.environ}
    async with MCPServerStdio(
        name="fiscai-yuki-api-connector",
        params={"command": sys.executable, "args": [str(ROOT / "server" / "run_server.py")], "env": env},
        cache_tools_list=True,
        client_session_timeout_seconds=60,
    ) as server:
        agent = Agent(name="Yuki assistant", instructions=INSTRUCTIONS, mcp_servers=[server])
        result = await Runner.run(agent, question)
        print(result.final_output)


if __name__ == "__main__":
    asyncio.run(main(" ".join(sys.argv[1:]) or "List the administrations."))
