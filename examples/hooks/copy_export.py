"""on_export hook: copy exported files to a second local folder. Reads the JSON payload on stdin; no secrets are ever in it."""
import json
import shutil
import sys
from pathlib import Path

payload = json.load(sys.stdin)
target = Path.home() / "yuki-export-copy"          # change to your own folder
target.mkdir(parents=True, exist_ok=True)
for f in payload.get("files", []):
    p = Path(f)
    if p.is_file():
        shutil.copy2(p, target / p.name)
