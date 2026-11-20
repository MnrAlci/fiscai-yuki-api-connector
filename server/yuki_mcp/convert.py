"""XML → JSON voor leesmethodes zonder eigen parser, plus geheimen-scrubber."""
from __future__ import annotations

import os
import re
from typing import Any, Optional
from xml.etree import ElementTree as ET

SECRET_ENV = ("YUKI_ACCESS_KEY", "YUKI_API_KEY", "YUKI_CACHE_KEY", "YUKI_DAILY_LIMIT_APPROVAL")
MAX_ROWS = 5000


def _local(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def element_to_data(el: ET.Element) -> Any:
    kids = [k for k in el if _local(k.tag) != "schema"]
    if not kids:
        txt = (el.text or "").strip()
        if el.attrib:
            d = {f"@{_local(k)}": v for k, v in el.attrib.items()}
            if txt:
                d["#text"] = txt
            return d
        return txt or None
    out: dict[str, Any] = {f"@{_local(k)}": v for k, v in el.attrib.items()}
    for k in kids:
        name = _local(k.tag)
        val = element_to_data(k)
        if name in out:
            if not isinstance(out[name], list):
                out[name] = [out[name]]
            out[name].append(val)
        else:
            out[name] = val
    return out


def rows_of(result: Optional[ET.Element]) -> tuple[list, Any]:
    """Geef (rijen, ruwe data). Daalt af door enkelvoudige wrappers (diffgram/NewDataSet)."""
    if result is None:
        return [], None
    node = result
    while True:
        kids = [k for k in node if _local(k.tag) != "schema"]
        if len(kids) == 1 and len(list(kids[0])) > 0:
            node = kids[0]
            continue
        break
    kids = [k for k in node if _local(k.tag) != "schema"]
    if not kids:
        txt = (node.text or "").strip()
        return ([], txt or None)
    if len({_local(k.tag) for k in kids}) == 1:
        rows = [element_to_data(k) for k in kids]
        return [r for r in rows if r not in (None, "", {})], None
    return [element_to_data(node)], None


def scrub(value: Any) -> Any:
    """Verwijder geheime waarden uit alles wat het proces verlaat."""
    secrets = [os.environ.get(n, "") for n in SECRET_ENV]
    secrets = [s for s in secrets if len(s) >= 6]

    def _s(x: Any) -> Any:
        if isinstance(x, str):
            for sec in secrets:
                x = x.replace(sec, "[GEHEIM]")
            x = re.sub(r"(?i)(<(?:accessKey|sessionID|sessionId|clientSecret)>).*?(</)", r"\1[GEHEIM]\2", x)
            return x
        if isinstance(x, dict):
            return {k: _s(v) for k, v in x.items()}
        if isinstance(x, (list, tuple)):
            return [_s(v) for v in x]
        return x
    return _s(value)
