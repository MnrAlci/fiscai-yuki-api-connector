#!/usr/bin/env python3
"""Opdrachtregel zonder installatie: python3 server/run_connector.py doctor"""
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.dont_write_bytecode = True
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE / "vendor"))
from yuki_mcp.cli import main  # noqa: E402

sys.exit(main())
