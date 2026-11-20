"""on_export hook: start a document generator after an export. Example with Pandoc (install it yourself; verify current docs).
Reads the export folder from the payload; edit TEMPLATE and the command to your needs."""
import json
import subprocess
import sys
from pathlib import Path

payload = json.load(sys.stdin)
folder = Path(payload.get("export_dir") or ".").expanduser()
template = Path("examples/templates/report.md")        # placeholder template with [Voorbeeld] content
if template.exists():
    subprocess.run(["pandoc", str(template), "-o", str(folder / "report.html")], check=False, timeout=60)
