#!/usr/bin/env python3
"""Startpunt van de MCP-server (stdio). Zoekt zelf de map van het pakket; gebruikt .venv indien aanwezig."""
import os
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
venv_py = ROOT / ".venv" / "bin" / "python"
if venv_py.exists() and Path(sys.executable).resolve() != venv_py.resolve() and not os.environ.get("YUKI_NO_VENV"):
    os.execv(str(venv_py), [str(venv_py), __file__, *sys.argv[1:]])
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "vendor"))
try:
    import httpx, cryptography  # noqa: F401,E401
except ImportError:
    sys.stderr.write("Ontbrekende afhankelijkheden. Installeer: python3 -m pip install -r requirements.txt\n")
    sys.exit(1)
from yuki_mcp.server import main  # noqa: E402

sys.exit(main())
