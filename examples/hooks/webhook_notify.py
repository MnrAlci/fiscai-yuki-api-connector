"""on_export hook: post a short notice to YOUR webhook (placeholder). Sends only tool, event and file count, never data.
Set YUKI_HOOK_WEBHOOK_URL yourself (not passed by the connector: add it to your own hook environment if needed). Makes a network call to that URL."""
import json
import os
import sys
import urllib.request

payload = json.load(sys.stdin)
url = os.environ.get("YUKI_HOOK_WEBHOOK_URL", "")
if not url.startswith("https://"):
    sys.exit(0)                                        # no URL set: do nothing
body = json.dumps({"tool": payload.get("tool"), "event": payload.get("event"), "files": len(payload.get("files", []))}).encode()
req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
urllib.request.urlopen(req, timeout=10)                # noqa: S310
