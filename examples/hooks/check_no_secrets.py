"""git pre-commit helper: reject files that look like they contain a Yuki or API key. Prints file names only, never the match."""
import re
import sys
from pathlib import Path

PATTERNS = [r"am_[A-Za-z0-9]{10,}", r"sk-[A-Za-z0-9]{16,}", r"(?i)YUKI_ACCESS_KEY\s*=\s*[A-Za-z0-9+/=_-]{16,}"]
bad = []
for f in sys.argv[1:]:
    try:
        t = Path(f).read_text(encoding="utf-8")
    except (UnicodeDecodeError, OSError):
        continue
    if any(re.search(p, t) for p in PATTERNS):
        bad.append(f)
if bad:
    print("Possible secret in: " + ", ".join(bad))
    sys.exit(1)
