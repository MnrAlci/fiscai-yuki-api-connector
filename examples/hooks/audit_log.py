"""post_call / client hook: append one audit line (time, event, tool) to a local file. Never writes arguments or results."""
import json
import sys
from pathlib import Path

try:
    d = json.load(sys.stdin)
except ValueError:
    d = {}
line = {"time": d.get("time"), "event": d.get("event") or d.get("hook_event_name"), "tool": d.get("tool") or d.get("tool_name")}
with open(Path.home() / "yuki-audit.log", "a", encoding="utf-8") as fh:
    fh.write(json.dumps(line) + "\n")
