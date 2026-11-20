"""Editie B: repo-hygiëne, naamgeving, versie-consistentie, Postman-collectie."""
import json
import re
try:
    import tomllib
except ImportError:  # Python 3.10
    import tomli as tomllib
from pathlib import Path

import pytest
from yuki_mcp import edition

ROOT = Path(__file__).resolve().parent.parent
pytestmark = pytest.mark.skipif(edition.EDITION != "marketplace", reason="alleen editie B")
ATTR = "Powered by FISCALCI Accounting & Tax (Askin Alci)"
SLUG, NAME, CLI = "fiscai-yuki-api-connector", "FISCAi Yuki API Connector", "yuki-api-connector"


def test_naamgeving_overal():
    pj = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))
    cj = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))
    assert pj["name"] == cj["name"] == SLUG and cj["displayName"] == NAME
    assert list(json.loads((ROOT / "mcp.json").read_text(encoding="utf-8"))["mcpServers"]) == [SLUG]
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))
    assert py["project"]["name"] == SLUG and CLI in py["project"]["scripts"]
    assert edition.PLUGIN_NAME == SLUG and edition.DISPLAY_NAME == NAME
    assert (ROOT / "skills" / SLUG / "SKILL.md").exists()


def test_geen_oude_naam_in_tekst():
    old = ["yuki-api-" + "client", "Yuki API " + "Client", "YUKI API " + "CLIENT"]
    for p in ROOT.rglob("*"):
        if not p.is_file() or p.suffix in (".png", ".pyc", ".jpg") or ".venv" in p.parts or "__pycache__" in p.parts or p.name == "test_repo_hygiene.py":
            continue
        try:
            t = p.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for o in old:
            assert o not in t, f"{o!r} in {p.relative_to(ROOT)}"


def test_tagline_en_nl_in_readme():
    assert "Plugin voor Grok Bot, werkt ook in Copilot, Claude, Cursor, Windsurf en andere MCP-clients" in (ROOT / "README.nl.md").read_text(encoding="utf-8")
    assert "Plugin for Grok Bot, also works in Copilot, Claude, Cursor, Windsurf and other MCP clients" in (ROOT / "README.md").read_text(encoding="utf-8")


def test_versie_consistent_en_changelog():
    from yuki_mcp import __version__
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    pj = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))["version"]
    cj = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))["version"]
    assert py == pj == cj == __version__
    assert re.search(rf"##\s*\[?{re.escape(py)}", (ROOT / "CHANGELOG.md").read_text(encoding="utf-8"))
    assert re.match(r"^\d+\.\d+\.\d+$", py)


def test_projectbestanden_aanwezig():
    for f in (".github/workflows/ci.yml", ".github/dependabot.yml", ".github/CODEOWNERS", ".github/PULL_REQUEST_TEMPLATE.md", ".github/labels.yml",
              ".github/rulesets/main-protection.json", ".github/rulesets/release-tags.json", ".pre-commit-config.yaml", "requirements-dev.txt",
              "Makefile", "Dockerfile", "CODE_OF_CONDUCT.md", "ROADMAP.md", "SECURITY.md", "docs/OPERATIONS.md", "docs/TROUBLESHOOTING.md",
              "docs/PRIVACY-DATA-FLOW.md", "docs/maintainers/REPO-SETTINGS.md", "docs/images/social-preview.png",
              "docs/CLI.md", "docs/CLI.nl.md", "docs/HOOKS.md", "docs/HOOKS.nl.md", "examples/hooks/hooks.example.toml", "examples/hooks/copy_export.py",
              "examples/hooks/audit_log.py", "server/run_connector.py", ".devcontainer/devcontainer.json"):
        assert (ROOT / f).exists(), f


def test_ci_en_rulesets_veilig():
    ci = (ROOT / ".github/workflows/ci.yml").read_text(encoding="utf-8")
    assert "permissions:\n  contents: read" in ci and "pytest" in ci and "ruff" in ci
    assert not re.search(r"secrets\.|YUKI_ACCESS_KEY|YUKI_WRITE_ENABLED", ci)
    for f in ("main-protection", "release-tags"):
        d = json.loads((ROOT / ".github/rulesets" / f"{f}.json").read_text(encoding="utf-8"))
        types = {r["type"] for r in d["rules"]}
        assert {"deletion", "non_fast_forward"} <= types
    assert "required_linear_history" in {r["type"] for r in json.loads((ROOT / ".github/rulesets/main-protection.json").read_text())["rules"]}


def test_dockerfile_zonder_geheimen():
    d = (ROOT / "Dockerfile").read_text(encoding="utf-8")
    assert "USER app" in d and not re.search(r"ENV\s+YUKI_ACCESS_KEY", d)


def test_nieuwe_docs_hebben_belgische_melding():
    for f in ("docs/TROUBLESHOOTING.md", "docs/PRIVACY-DATA-FLOW.md", "docs/POSTMAN.md", "docs/POSTMAN.nl.md"):
        t = (ROOT / f).read_text(encoding="utf-8")
        assert "Belgian" in t or "Belgische" in t, f
    assert ATTR in (ROOT / "docs/POSTMAN.md").read_text(encoding="utf-8")


# ---- Postman
COL = ROOT / "postman" / "FISCAi-Yuki-API-Connector.postman_collection.json"
ENV = ROOT / "postman" / "FISCAi-Yuki-API-Connector.postman_environment.json"


def _requests(items, in_disabled=False):
    for it in items:
        dis = in_disabled or "DISABLED" in it["name"]
        if "item" in it:
            yield from _requests(it["item"], dis)
        else:
            yield it, dis


def test_postman_collectie_parst_en_is_v21():
    c = json.loads(COL.read_text(encoding="utf-8"))
    assert c["info"]["schema"].endswith("/v2.1.0/collection.json")
    assert "Not an official Yuki or Visma product" in c["info"]["description"]
    reqs = list(_requests(c["item"]))
    assert len(reqs) >= 40
    json.loads(ENV.read_text(encoding="utf-8"))


def test_postman_geen_geheimen_en_alleen_leesmethodes():
    from yuki_mcp.transport import is_allowed
    text = COL.read_text(encoding="utf-8") + ENV.read_text(encoding="utf-8")
    for pat in (r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}(?!\")", r"\b[0-9a-f]{32,}\b", r"sk-[A-Za-z0-9]{16,}"):
        for m in re.finditer(pat, text):
            # alleen de afgeleide _postman_id (uuid5) is toegestaan
            assert m.group(0) in (json.loads(COL.read_text())["info"]["_postman_id"], json.loads(ENV.read_text())["id"]), m.group(0)
    env = json.loads(ENV.read_text(encoding="utf-8"))
    for v in env["values"]:
        if v["key"] in ("yuki_access_key", "administration_id", "domain_id"):
            assert v["value"] == ""
    c = json.loads(COL.read_text(encoding="utf-8"))
    assert c["variable"][0]["value"] == ""
    n_dis = 0
    for it, dis in _requests(c["item"]):
        req = it["request"]
        assert req["url"]["raw"].startswith("{{base_url}}/") and req["method"] == "POST"
        service, method = it["name"].replace("DISABLED - ", "").split(".", 1)
        if dis:
            n_dis += 1
            assert "DISABLED" in it["name"] and "requires explicit approval" in req["description"]
        else:
            assert is_allowed(service, method), it["name"]
        assert "{{yuki_access_key}}" in req["body"]["raw"] or "{{session_id}}" in req["body"]["raw"]
    assert n_dis == 2


def test_postman_authenticate_test_script_bewaart_sessie_zonder_loggen():
    c = json.loads(COL.read_text(encoding="utf-8"))
    auth = c["item"][0]["item"][0]
    js = "\n".join(auth["event"][0]["script"]["exec"])
    assert "collectionVariables.set(\"session_id\"" in js and "console.log" not in js


# ---- agents
AGENT_FILES = [
    "AGENTS.md", "agents/README.md", "agents/core/instructions.md", "agents/core/profile-business-owner.md", "agents/core/profile-accountant.md",
    "agents/grok-bot/business-owner.md", "agents/grok-bot/accountant.md",
    "agents/claude/claude-code/yuki-business-owner.md", "agents/claude/claude-code/yuki-accountant.md",
    "agents/claude/claude-desktop/project-instructions-business-owner.md", "agents/claude/claude-desktop/project-instructions-accountant.md",
    ".github/agents/yuki-business-owner.agent.md", ".github/agents/yuki-accountant.agent.md", "agents/github-copilot/copilot-instructions.md",
    "agents/cursor/yuki-core.mdc", "agents/cursor/yuki-business-owner.mdc", "agents/cursor/yuki-accountant.mdc",
    "agents/openai-agents-sdk/agent.py", "agents/generic/system-prompt-business-owner.txt", "agents/generic/system-prompt-accountant.txt",
]


def test_agentbestanden_bestaan_hebben_attributie_en_geen_geheimen():
    for f in AGENT_FILES:
        t = (ROOT / f).read_text(encoding="utf-8")
        assert ATTR in t, f
        for pat in (r"am_[A-Za-z0-9]{10,}", r"\b[0-9a-f]{32,}\b", r"sk-[A-Za-z0-9]{16,}", r"(?i)bearer\s+[A-Za-z0-9._-]{20,}"):
            assert not re.search(pat, t), (f, pat)
        assert "YUKI_WRITE_ENABLED=ja" not in t and "YUKI_WRITE_ENABLED=true" not in t, f
        if f != "AGENTS.md" and not f.endswith("agent.py") and "README" not in f:
            assert "Belgian" in t or "Belgische" in t, f


def test_agent_formaten():
    cc = (ROOT / "agents/claude/claude-code/yuki-business-owner.md").read_text(encoding="utf-8")
    assert cc.startswith("---\nname: yuki-business-owner\ndescription:") and f"mcp__{SLUG}__*" in cc
    cp = (ROOT / ".github/agents/yuki-accountant.agent.md").read_text(encoding="utf-8")
    assert cp.startswith("---\nname:") and "description:" in cp.split("---")[1]
    mdc = (ROOT / "agents/cursor/yuki-accountant.mdc").read_text(encoding="utf-8")
    assert mdc.startswith("---\ndescription:") and "alwaysApply: false" in mdc
    py = (ROOT / "agents/openai-agents-sdk/agent.py").read_text(encoding="utf-8")
    compile(py, "agent.py", "exec")
    assert "MCPServerStdio" in py and "YUKI_WRITE_ENABLED" in py and "os.environ[" in py
    core = (ROOT / "agents/core/instructions.md").read_text(encoding="utf-8")
    assert "Read-only by default" in core and "Afhandelen" in core


def test_beschrijving_gelijk_en_kort():
    pj = json.loads((ROOT / "plugin.json").read_text(encoding="utf-8"))["description"]
    cj = json.loads((ROOT / ".cursor-plugin" / "plugin.json").read_text(encoding="utf-8"))["description"]
    py = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["description"]
    assert pj == cj == py and len(pj) <= 350 and pj.endswith(ATTR) and "Yuki" in pj and "Grok Bot" in pj


def test_hook_voorbeelden_compileren_en_toml_parst():
    for p in (ROOT / "examples" / "hooks").glob("*.py"):
        compile(p.read_text(encoding="utf-8"), str(p), "exec")
    cfg = tomllib.loads((ROOT / "examples/hooks/hooks.example.toml").read_text(encoding="utf-8"))
    assert cfg["enabled"] is True and {h["event"] for h in cfg["hooks"]} <= {"pre_call", "post_call", "on_error", "on_export"}
    for f in ("HOOKS.md", "HOOKS.nl.md"):
        t = (ROOT / "docs" / f).read_text(encoding="utf-8")
        assert "verify current docs" in t or "verifieer actuele documentatie" in t
        assert ATTR in t


def test_cli_docs_exitcodes_en_precedence():
    t = (ROOT / "docs/CLI.md").read_text(encoding="utf-8")
    assert "CLI options > environment variables > files" in t and "| 6 |" in t
    assert "YUKI_WRITE_ENABLED" not in t
