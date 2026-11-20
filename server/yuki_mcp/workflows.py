"""Automatisering: vergaderingvoorbereiding en terugkerende verplichtingen. Alleen lezen voor Yuki; mails alleen als concept.

* ``plan``: bepaalt welke voorbereidingen nodig zijn (agenda + verplichtingenkalender), zonder Yuki-calls.
* ``run``: maakt per item een overzicht (Markdown + JSON) via bestaande alleen-lezen tools en optioneel een concept-e-mail.
* ``list``: toont de configuratie (klanten, verplichtingen met bron en 'verifieer actuele regel').

Deadlines staan NIET in de code: ze komen uit de configuratie van de gebruiker (voorbeeld: examples/workflows/). Geen geheimen in de config.
Exitcodes: zie cli.py (3 configuratie, 4 tool-fout, 5 netwerk/agenda, 6 geweigerd).
"""
from __future__ import annotations

import calendar as _cal
import json
import logging
import re
import sys
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Callable, Optional

from .wf_calendars import CalendarError, make_adapter
from .wf_drafts import Draft, DraftError, SendRefused, make_drafter, send_allowed, slug
from .wf_ics import Event, get_tz

LOG = logging.getLogger("yuki.workflows")
ALLOWED_TOOLS = ("yuki_dashboard_kpis", "yuki_ouderdom_openstaande_posten", "yuki_boekjaar_gewijzigd", "yuki_export_dataset")
FREQUENCIES = ("monthly", "quarterly", "annual", "fixed")
SECTIONS = ("kpis", "open_items", "missing_documents", "dossier_status", "export")
SECRET_KEY = re.compile(r"(password|passwd|secret|token|api_?key|access_?key|credential)", re.I)
DEFAULT_KPIS = ["omzet", "kosten", "resultaat", "liquide_middelen", "open_debiteuren.totaal", "open_debiteuren.vervallen",
                "open_crediteuren.totaal", "open_crediteuren.vervallen", "btw_indicatie"]


class WorkflowError(Exception):
    pass


# ------------------------------------------------------------------ configuratie
def _walk(node: Any, path: str = "") -> None:
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("url", "ics_url") or (SECRET_KEY.search(str(k)) and not str(k).endswith("_env")):
                raise WorkflowError(f"Config '{path}{k}': geheimen en privé-URL's horen niet in het bestand. Gebruik een '*_env'-sleutel met de NAAM van een omgevingsvariabele.")
            _walk(v, f"{path}{k}.")
    elif isinstance(node, list):
        for i, v in enumerate(node):
            _walk(v, f"{path}{i}.")


def load_config(path: Path) -> dict:
    p = Path(path).expanduser()
    if not p.is_file():
        raise WorkflowError(f"Workflows-bestand niet gevonden: {p}")
    text = p.read_text(encoding="utf-8-sig")
    if p.suffix.lower() == ".json":
        cfg = json.loads(text)
    else:
        try:
            import tomllib
        except ImportError:
            import tomli as tomllib  # type: ignore
        cfg = tomllib.loads(text)
    validate(cfg)
    cfg["_base"] = str(p.resolve().parent)
    return cfg


def validate(cfg: dict) -> None:
    _walk(cfg)
    s = cfg.get("settings", {})
    d = s.get("days_ahead", 2)
    if not isinstance(d, int) or isinstance(d, bool) or not 0 <= d <= 60:
        raise WorkflowError("settings.days_ahead moet een geheel getal van 0 tot 60 zijn.")
    if s.get("language", "nl") not in ("nl", "en"):
        raise WorkflowError("settings.language moet 'nl' of 'en' zijn.")
    mx = s.get("max_items", 10)
    if not isinstance(mx, int) or isinstance(mx, bool) or not 1 <= mx <= 50:
        raise WorkflowError("settings.max_items moet 1 tot 50 zijn (bescherming van het daglimiet).")
    clients = cfg.get("clients", [])
    if not isinstance(clients, list):
        raise WorkflowError("'clients' moet een lijst van [[clients]] zijn.")
    names = set()
    for c in clients:
        if not c.get("name") or not c.get("administratie"):
            raise WorkflowError("Elke [[clients]] heeft 'name' en 'administratie' nodig.")
        if c["name"] in names:
            raise WorkflowError(f"Dubbele klantnaam: {c['name']}")
        names.add(c["name"])
    ids = set()
    for o in cfg.get("obligations", []):
        oid = o.get("id")
        if not oid or oid in ids:
            raise WorkflowError(f"Verplichting zonder (unieke) id: {oid!r}")
        ids.add(oid)
        if o.get("frequency") not in FREQUENCIES:
            raise WorkflowError(f"Verplichting {oid}: frequency moet {', '.join(FREQUENCIES)} zijn.")
        if not isinstance(o.get("lead_days", 14), int) or o.get("lead_days", 14) < 0:
            raise WorkflowError(f"Verplichting {oid}: lead_days moet een geheel getal >= 0 zijn.")
        if o["frequency"] == "fixed":
            for x in o.get("dates", []):
                date.fromisoformat(str(x))
        elif not o.get("due_day") or (o["frequency"] == "annual" and not o.get("due_month")):
            raise WorkflowError(f"Verplichting {oid}: due_day (en due_month bij annual) ontbreekt; vul de actuele regel zelf in.")
        if not o.get("source"):
            raise WorkflowError(f"Verplichting {oid}: 'source' (officiële bron, alleen link) is verplicht.")
    for c in clients:
        for oid in c.get("obligations", []):
            if oid not in ids:
                raise WorkflowError(f"Klant {c['name']}: onbekende verplichting '{oid}'.")
    for sec in cfg.get("template", {}).get("sections", []):
        if sec not in SECTIONS:
            raise WorkflowError(f"template.sections: onbekende sectie '{sec}'. Kies uit {', '.join(SECTIONS)}.")


# ------------------------------------------------------------------ verplichtingen
def _add_months(y: int, m: int, n: int) -> tuple[int, int]:
    t = y * 12 + (m - 1) + n
    return t // 12, t % 12 + 1


def _clamp(y: int, m: int, d: int) -> date:
    return date(y, m, min(d, _cal.monthrange(y, m)[1]))


def due_dates(ob: dict, start: date, end: date) -> list[dict]:
    """Vervaldatums in [start, end] volgens de REGEL IN DE CONFIG (geen ingebouwde deadlines)."""
    out: list[dict] = []
    f = ob["frequency"]
    if f == "fixed":
        for x in ob.get("dates", []):
            d = date.fromisoformat(str(x))
            if start <= d <= end:
                out.append({"due": d, "period": str(x), "jaar": d.year + int(ob.get("year_offset", -1)), "periode": "jaar"})
        return out
    off = int(ob.get("due_month_offset", 1))
    dd = int(ob["due_day"])
    for y in range(start.year - 2, end.year + 2):
        if f == "annual":
            d = _clamp(y + int(ob.get("due_year_offset", 0)), int(ob["due_month"]), dd)
            if start <= d <= end:
                out.append({"due": d, "period": str(y), "jaar": y + int(ob.get("year_offset", -1)), "periode": "jaar"})
            continue
        for m in range(1, 13):
            if f == "quarterly" and m % 3:
                continue
            yy, mm = _add_months(y, m, off)
            d = _clamp(yy, mm, dd)
            if start <= d <= end:
                label = f"{y}-Q{m // 3}" if f == "quarterly" else f"{y}-{m:02d}"
                out.append({"due": d, "period": label, "jaar": y, "periode": f"kwartaal:{m // 3}" if f == "quarterly" else f"maand:{m}"})
    return sorted(out, key=lambda x: x["due"])


# ------------------------------------------------------------------ plan
@dataclass
class Item:
    kind: str                      # meeting | obligation
    key: str
    client: dict
    title: str
    when: str                      # ISO datum/tijd
    detail: dict = field(default_factory=dict)

    def brief(self) -> dict:
        extra = {k: v for k, v in self.detail.items() if k in ("due", "period", "overdue", "attendees")}
        if "obligation" in self.detail:
            extra["obligation"] = self.detail["obligation"]["id"]
        return {"kind": self.kind, "key": self.key, "client": self.client["name"], "title": self.title, "when": self.when, **extra}


def match_client(ev: Event, clients: list[dict]) -> Optional[dict]:
    text = f"{ev.summary}\n{ev.description}".casefold()
    people = set(ev.attendees) | ({ev.organizer} if ev.organizer else set())
    for c in clients:
        if any(k.casefold() in text for k in c.get("match_keywords", [])):
            return c
        if any(e.casefold() in people for e in c.get("match_emails", [])):
            return c
        doms = {p.rsplit("@", 1)[-1] for p in people if "@" in p}
        if any(d.casefold().lstrip("@") in doms for d in c.get("match_domains", [])):
            return c
    return None


def today_in(cfg: dict, now: Optional[datetime] = None) -> date:
    tz = get_tz(cfg.get("settings", {}).get("timezone", "Europe/Brussels"))
    return (now or datetime.now(tz)).astimezone(tz).date()


def plan_obligations(cfg: dict, today: date) -> list[Item]:
    obs = {o["id"]: o for o in cfg.get("obligations", [])}
    items: list[Item] = []
    grace = int(cfg.get("settings", {}).get("overdue_days", 14))
    for c in cfg.get("clients", []):
        for oid in c.get("obligations", []):
            o = obs[oid]
            lead = int(o.get("lead_days", 14))
            for occ in due_dates(o, today - timedelta(days=grace), today + timedelta(days=lead)):
                if occ["due"] - timedelta(days=lead) <= today:
                    items.append(Item("obligation", f"{c['name']}|{oid}|{occ['period']}|{occ['due']}", c, f"{o.get('title', oid)} ({occ['period']})", occ["due"].isoformat(),
                                      {"obligation": o, "period": occ["period"], "due": occ["due"].isoformat(), "overdue": occ["due"] < today, "jaar": occ["jaar"], "periode": occ["periode"]}))
    return sorted(items, key=lambda i: i.when)


def plan_meetings(cfg: dict, today: date, days: int, adapter) -> tuple[list[Item], list[dict]]:
    tz = get_tz(cfg.get("settings", {}).get("timezone", "Europe/Brussels"))
    start = datetime(today.year, today.month, today.day, tzinfo=tz)
    end = start + timedelta(days=days + 1)
    items: list[Item] = []
    skipped: list[dict] = []
    for ev in adapter.events(start, end):
        c = match_client(ev, cfg.get("clients", []))
        if c is None:
            skipped.append({"summary": ev.summary, "start": ev.start.isoformat()})
            continue
        items.append(Item("meeting", f"{c['name']}|meeting|{ev.key}", c, ev.summary or "Vergadering", ev.start.isoformat(timespec="minutes"),
                          {"attendees": sorted(ev.attendees), "location": ev.location, "date": ev.start.date().isoformat()}))
    return items, skipped


# ------------------------------------------------------------------ teksten
TXT = {
    "nl": {"prep": "Voorbereiding", "meeting": "Vergadering", "when": "Wanneer", "client": "Klant", "kpis": "Kerncijfers", "open_items": "Openstaande posten",
           "missing_documents": "Ontbrekende documenten", "dossier_status": "Dossierstatus", "export": "Export", "none": "Geen", "n_a": "n.v.t.", "unavailable": "niet beschikbaar",
           "no_status": "Geen statusbestand ingesteld: niet nagegaan wat ontvangen is; alle gevraagde documenten staan hieronder.", "checklist": "Checklist", "source": "Bron (verifieer actuele regel)",
           "due": "Vervaldatum", "overdue": "VERLOPEN", "verify": "verifieer actuele regel", "footer": "Automatisch overzicht uit Yuki (alleen lezen). Controleer de cijfers; geen fiscaal advies.",
           "subject_meeting": "Voorbereiding vergadering {date}: ontbrekende documenten", "subject_obligation": "{title}: ontbrekende stukken (uiterlijk {due})",
           "body": "Beste,\n\nIn het kader van {context} ontbreken nog de volgende stukken:\n\n{missing_list}\n\nKunt u die vóór {deadline} bezorgen?\n\nAlvast bedankt.\n\n{signature}",
           "closed": "Ontbrekend", "kpi_labels": {}},
    "en": {"prep": "Preparation", "meeting": "Meeting", "when": "When", "client": "Client", "kpis": "Key figures", "open_items": "Open items", "missing_documents": "Missing documents",
           "dossier_status": "File status", "export": "Export", "none": "None", "n_a": "n/a", "unavailable": "unavailable",
           "no_status": "No status file configured: what was received was not checked; all requested documents are listed below.", "checklist": "Checklist", "source": "Source (verify current rule)",
           "due": "Due date", "overdue": "OVERDUE", "verify": "verify current rule", "footer": "Automatic overview from Yuki (read-only). Check the figures; not tax advice.",
           "subject_meeting": "Preparing our meeting on {date}: missing documents", "subject_obligation": "{title}: missing documents (due {due})",
           "body": "Hello,\n\nFor {context} we are still missing the following documents:\n\n{missing_list}\n\nCould you send them before {deadline}?\n\nThank you.\n\n{signature}",
           "closed": "Missing", "kpi_labels": {}},
}
ATTR = "Powered by FISCALCI Accounting & Tax (Askin Alci)"
BE_NL = "Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels."


def _dig(d: Any, path: str) -> Any:
    for p in path.split("."):
        if not isinstance(d, dict) or p not in d:
            return None
        d = d[p]
    return d


# ------------------------------------------------------------------ overzicht
class ToolRunner:
    """Enige toegang tot Yuki: alleen toegelaten, alleen-lezen tools, via de hooks (pre_call/post_call/on_error/on_export)."""

    def __init__(self, tools, hooks) -> None:
        self.tools, self.hooks = tools, hooks

    def __call__(self, name: str, args: dict) -> dict:
        from .hooks import guarded_call
        if name not in ALLOWED_TOOLS:
            raise SendRefused(f"{name} is niet toegelaten in workflows.")
        d = self.tools.defs.get(name)
        if d is None or not d.get("annotations", {}).get("readOnlyHint", False):
            raise SendRefused(f"{name} is niet alleen-lezen.")
        return guarded_call(self.hooks, self.tools.call, name, args)


def _read_status(client: dict, base: str) -> Optional[dict]:
    sf = client.get("status_file")
    if not sf:
        return None
    p = Path(sf)
    p = p if p.is_absolute() else Path(base) / p
    if not p.is_file():
        return None
    return json.loads(p.read_text(encoding="utf-8-sig"))


def required_documents(item: Item, cfg: dict, today: date) -> list[str]:
    docs = list(item.client.get("documents", []))
    if item.kind == "obligation":
        docs += item.detail["obligation"].get("documents", [])
    else:
        for o in plan_obligations({**cfg, "clients": [item.client]}, today):
            docs += o.detail["obligation"].get("documents", [])
    seen: list[str] = []
    for d in docs:
        if d not in seen:
            seen.append(d)
    return seen


def build_overview(item: Item, cfg: dict, call: Callable[[str, dict], dict], today: date, lang: str = "nl") -> dict:
    t = TXT[lang]
    tpl = cfg.get("template", {})
    sections = tpl.get("sections") or ["kpis", "open_items", "missing_documents", "dossier_status"]
    adm = item.client["administratie"]
    errors: list[dict] = []
    out: dict[str, Any] = {"title": f"{t['prep']}: {item.client['name']}: {item.title}", "kind": item.kind, "when": item.when, "client": item.client["name"], "sections": {}, "errors": errors,
                           "read_only": True}
    year = int(item.detail.get("jaar", today.year))
    period = item.detail.get("periode") or tpl.get("kpi_period", "jaar")

    def safe(label: str, name: str, args: dict):
        try:
            return call(name, args)
        except SendRefused:
            raise
        except Exception as exc:  # noqa: BLE001 - één sectie mag de rest niet breken
            from .convert import scrub
            errors.append({"section": label, "tool": name, "error": scrub(f"{type(exc).__name__}: {exc}")})
            return None

    for sec in sections:
        if sec == "kpis":
            args = {"administratie": adm, "jaar": year, "periode": period, "vergelijk_vorige_periode": bool(tpl.get("compare", True))}
            if item.client.get("domein"):
                args["domein"] = item.client["domein"]
            res = safe(sec, "yuki_dashboard_kpis", args)
            if res is not None:
                out["sections"][sec] = {"rows": [{"kpi": k, "waarde": _dig(res, k)} for k in tpl.get("kpis", DEFAULT_KPIS)], "periode": res.get("periode")}
        elif sec == "open_items":
            rows = {}
            for soort in tpl.get("open_items_kind", ["debiteuren", "crediteuren"]):
                args = {"administratie": adm, "soort": soort}
                if item.client.get("domein"):
                    args["domein"] = item.client["domein"]
                res = safe(sec, "yuki_ouderdom_openstaande_posten", args)
                if res is not None:
                    rows[soort] = {k: res.get(k) for k in ("peildatum", "totaal_positief", "vervallen_totaal", "buckets")} | {"negatieve_posten": _dig(res, "negatieve_posten.aantal")}
            if rows:
                out["sections"][sec] = rows
        elif sec == "dossier_status":
            st = _read_status(item.client, cfg.get("_base", "."))
            data: dict[str, Any] = {"status_file": st, "financial_year_modified": None}
            if item.client.get("financial_year_id"):
                args = {"administratie": adm, "jaar_id": int(item.client["financial_year_id"])}
                res = safe(sec, "yuki_boekjaar_gewijzigd", args)
                data["financial_year_modified"] = res
            out["sections"][sec] = data
        elif sec == "missing_documents":
            required = required_documents(item, cfg, today)
            st = _read_status(item.client, cfg.get("_base", "."))
            got = {str(x).casefold() for x in (st or {}).get("received", [])}
            missing = [d for d in required if d.casefold() not in got]
            out["sections"][sec] = {"required": required, "missing": missing, "checked_against_status_file": st is not None}
        elif sec == "export":
            fmts = tpl.get("export_formats", [])
            if fmts:
                folder = Path(cfg.get("_out", ".")) / "exports" / slug(item.client["name"])
                args = {"dataset": "kpis", "administratie": adm, "jaar": year, "periode": period, "formaten": fmts, "export_map": str(folder)}
                res = safe(sec, "yuki_export_dataset", args)
                if res is not None:
                    out["sections"][sec] = {"files": res.get("bestanden") if isinstance(res, dict) else None}
    miss = (out["sections"].get("missing_documents") or {}).get("missing")
    if miss is None:
        miss = required_documents(item, cfg, today) if "missing_documents" not in sections else []
    out["missing"] = miss
    return out


def render_md(ov: dict, item: Item, lang: str = "nl") -> str:
    t = TXT[lang]
    L = [f"# {ov['title']}", "", f"- {t['client']}: {item.client['name']}", f"- {t['when']}: {ov['when']}"]
    if item.kind == "obligation":
        o = item.detail["obligation"]
        L += [f"- {t['due']}: {item.detail['due']}" + (f" ({t['overdue']})" if item.detail["overdue"] else ""), f"- {t['source']}: {o.get('source')} ({o.get('verify', t['verify'])})"]
    L.append("")
    s = ov["sections"]
    if "kpis" in s:
        L += [f"## {t['kpis']}", "", "| KPI | Waarde |", "|---|---|"] + [f"| {r['kpi']} | {r['waarde'] if r['waarde'] is not None else t['n_a']} |" for r in s["kpis"]["rows"]] + [""]
    if "open_items" in s:
        L += [f"## {t['open_items']}", ""]
        for soort, d in s["open_items"].items():
            L.append(f"- {soort}: totaal {d.get('totaal_positief')}, vervallen {d.get('vervallen_totaal')}, negatieve posten na te gaan: {d.get('negatieve_posten')}")
        L.append("")
    if "missing_documents" in s:
        md = s["missing_documents"]
        L += [f"## {t['missing_documents']}", ""]
        if not md["checked_against_status_file"]:
            L += [f"_{t['no_status']}_", ""]
        L += [f"- [ ] {d}" for d in md["missing"]] or [t["none"]]
        L.append("")
    if "dossier_status" in s:
        d = s["dossier_status"]
        L += [f"## {t['dossier_status']}", ""]
        sf = d.get("status_file") or {}
        for k in ("last_reviewed", "notes"):
            if sf.get(k):
                L.append(f"- {k}: {sf[k]}")
        if d.get("financial_year_modified"):
            L.append(f"- boekjaar laatst gewijzigd: {d['financial_year_modified']}")
        L.append("")
    if item.kind == "obligation" and item.detail["obligation"].get("checklist"):
        L += [f"## {t['checklist']}", ""] + [f"- [ ] {c}" for c in item.detail["obligation"]["checklist"]] + [""]
    if "export" in s and s["export"].get("files"):
        L += [f"## {t['export']}", ""] + [f"- {f}" for f in s["export"]["files"]] + [""]
    if ov["errors"]:
        L += ["## Fouten", ""] + [f"- {e['section']}: {e['error']}" for e in ov["errors"]] + [""]
    L += [t["footer"], "", ATTR, "", f"_{BE_NL}_" if lang == "nl" else "_Intended for Belgian bookkeepers/accountants; based on Belgian accounting and VAT rules (MAR, Belgian VAT system). Use outside Belgium: verify the local rules yourself._", ""]
    return "\n".join(L)


def build_draft(item: Item, ov: dict, cfg: dict, lang: str = "nl") -> Optional[Draft]:
    if not ov["missing"]:
        return None
    t = TXT[lang]
    m = cfg.get("mail", {})
    tpl = m.get("templates", {}).get(item.kind, {})
    missing_list = "\n".join(f"- {d}" for d in ov["missing"])
    if item.kind == "meeting":
        subject = tpl.get("subject", t["subject_meeting"]).format_map(_Safe(date=item.detail.get("date", ""), client=item.client["name"], title=item.title))
        context, deadline = f"onze vergadering van {item.detail.get('date', '')}" if lang == "nl" else f"our meeting on {item.detail.get('date', '')}", item.detail.get("date", "")
    else:
        subject = tpl.get("subject", t["subject_obligation"]).format_map(_Safe(title=item.title, due=item.detail["due"], client=item.client["name"]))
        context, deadline = item.title, item.detail["due"]
    body = tpl.get("body", t["body"]).format_map(_Safe(context=context, missing_list=missing_list, deadline=deadline, client=item.client["name"], signature=m.get("signature", ""), date=item.detail.get("date", "")))
    return Draft(to=list(item.client.get("email_to", [])), cc=list(m.get("cc", [])), subject=subject, body=body)


class _Safe(dict):
    def __missing__(self, key: str) -> str:
        return "{" + key + "}"


# ------------------------------------------------------------------ uitvoeren
def _state(out: Path) -> dict:
    p = out / "state.json"
    return json.loads(p.read_text(encoding="utf-8")) if p.is_file() else {}


def run_items(items: list[Item], cfg: dict, call, out_dir: Path, today: date, lang: str, drafter, create_drafts: bool, send: bool, force: bool, hooks=None) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    cfg = {**cfg, "_out": str(out_dir)}
    st = _state(out_dir)
    day = out_dir / today.isoformat()
    day.mkdir(parents=True, exist_ok=True)
    results: list[dict] = []
    limit = int(cfg.get("settings", {}).get("max_items", 10))
    for item in items:
        if item.key in st and not force:
            results.append({**item.brief(), "status": "al_gedaan"})
            continue
        if sum(1 for r in results if r["status"] in ("klaar", "fouten")) >= limit:
            results.append({**item.brief(), "status": "overgeslagen_max_items"})
            continue
        ov = build_overview(item, cfg, call, today, lang)
        base = f"{slug(item.client['name'])}-{item.kind}-{slug(item.when)}"
        md, js = day / f"{base}.md", day / f"{base}.json"
        md.write_text(render_md(ov, item, lang), encoding="utf-8")
        js.write_text(json.dumps(ov, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
        files = [str(md), str(js)]
        draft_ref = None
        sent = False
        d = build_draft(item, ov, cfg, lang) if create_drafts else None
        if d is not None:
            draft_ref = drafter.draft(d, f"{base}-herinnering")
            files.append(draft_ref)
            if send:
                if not getattr(drafter, "can_send", False):
                    raise SendRefused(f"Adapter '{drafter.name}' kan niet versturen; alleen 'smtp' ondersteunt dat (na bevestiging).")
                if not d.to:
                    raise DraftError(f"{item.client['name']}: geen email_to ingesteld; niet verstuurd.")
                drafter.send(d)
                sent = True
        if hooks is not None:
            hooks.fire("on_export", {"tool": "workflows", "files": files, "export_dir": str(day)})
        status = "fouten" if ov["errors"] else "klaar"
        if status == "klaar":
            st[item.key] = {"done": today.isoformat(), "files": files, "sent": sent}
        results.append({**item.brief(), "status": status, "files": files, "missing": ov["missing"], "draft": draft_ref, "sent": sent, "errors": ov["errors"]})
    (out_dir / "state.json").write_text(json.dumps(st, ensure_ascii=False, indent=2), encoding="utf-8")
    return {"date": today.isoformat(), "results": results}


# ------------------------------------------------------------------ opdrachtregel
def _only(a) -> tuple[bool, bool]:
    o = getattr(a, "only", None)
    return o in (None, "meetings"), o in (None, "obligations")


def cmd_workflows(a, out, emit_err=lambda m: sys.stderr.write(m + "\n"), tools_factory=None, http_get=None, http_post=None, interactive=None, ask=None) -> int:
    from .cli import EXIT_CONFIG, EXIT_NET, EXIT_OK, EXIT_REFUSED, EXIT_TOOL, EXIT_USAGE
    action = getattr(a, "wf_cmd", None)
    if action not in ("run", "list", "plan", "init"):
        emit_err("Gebruik: yuki-api-connector workflows run|list|plan|init")
        return EXIT_USAGE
    if action == "init":
        return _init(a, out)
    try:
        cfg = load_config(Path(a.workflows_file))
    except (WorkflowError, ValueError, OSError) as exc:
        emit_err(f"Configuratiefout: {exc}")
        return EXIT_CONFIG
    except Exception as exc:  # noqa: BLE001 - TOML-fout e.d.
        emit_err(f"Configuratiefout: {type(exc).__name__}: {exc}")
        return EXIT_CONFIG
    s = cfg.get("settings", {})
    lang = s.get("language", "nl")
    if action == "list":
        data = {"clients": [{"name": c["name"], "obligations": c.get("obligations", []), "match": {k: c.get(k, []) for k in ("match_keywords", "match_emails", "match_domains")}} for c in cfg.get("clients", [])],
                "obligations": [{"id": o["id"], "title": o.get("title"), "frequency": o["frequency"], "lead_days": o.get("lead_days", 14), "source": o["source"], "verify": o.get("verify", "verifieer actuele regel")} for o in cfg.get("obligations", [])],
                "calendar": cfg.get("calendar", {}).get("adapter", "ics"), "mail": cfg.get("mail", {}).get("adapter", "eml"), "days_ahead": s.get("days_ahead", 2)}
        out.emit(data, "\n".join([f"Klanten ({len(data['clients'])}):"] + [f"  - {c['name']}: {', '.join(c['obligations']) or '-'}" for c in data["clients"]] +
                                 [f"Verplichtingen ({len(data['obligations'])}):"] + [f"  - {o['id']} [{o['frequency']}, {o['lead_days']} d vooraf]: {o['source']} ({o['verify']})" for o in data["obligations"]]))
        return EXIT_OK
    today = date.fromisoformat(a.today) if getattr(a, "today", None) else today_in(cfg)
    days = a.days if getattr(a, "days", None) is not None else int(s.get("days_ahead", 2))
    want_m, want_o = _only(a)
    items: list[Item] = []
    skipped: list[dict] = []
    try:
        if want_m and cfg.get("calendar"):
            cal = dict(cfg["calendar"])
            if cal.get("path") and not Path(cal["path"]).expanduser().is_absolute():
                cal["path"] = str(Path(cfg["_base"]) / cal["path"])
            ad = make_adapter(cal, s.get("timezone", "Europe/Brussels"), http_get)
            mi, skipped = plan_meetings(cfg, today, days, ad)
            items += mi
        if want_o:
            items += plan_obligations(cfg, today)
    except (CalendarError, OSError) as exc:
        emit_err(f"Agendafout: {exc}")
        return EXIT_NET
    items.sort(key=lambda i: i.when)
    if action == "plan" or getattr(a, "dry_run", False):
        out.emit({"date": today.isoformat(), "days_ahead": days, "dry_run": action == "run", "network_yuki": False, "items": [i.brief() for i in items], "unmatched_events": len(skipped)},
                 "\n".join([f"{today}: {len(items)} voorbereiding(en), {len(skipped)} niet-gekoppelde agenda-item(s)" + (" [dry-run: niets uitgevoerd]" if action == "run" else "")] +
                           [f"  - {i.kind:10} {i.when[:16]:16} {i.client['name']}: {i.title}" for i in items]))
        return EXIT_OK
    mail = cfg.get("mail", {})
    out_dir = Path(getattr(a, "out", None) or s.get("out_dir", "workflow-output")).expanduser()
    if not out_dir.is_absolute() and not getattr(a, "out", None):
        out_dir = Path(cfg["_base"]) / out_dir
    try:
        interactive = sys.stdin.isatty() if interactive is None else interactive
        send = send_allowed(mail, bool(getattr(a, "send", False)), bool(getattr(a, "confirm_send", False)), interactive, ask or input)
        drafter = make_drafter(mail, out_dir / "drafts", http_post, smtp_factory=None)
        if tools_factory is None:
            from .clientfactory import ClientFactory
            from .hooks import Hooks
            from .tools import Tools
            hooks = Hooks.from_env()
            call = ToolRunner(Tools(ClientFactory()), hooks)
        else:
            call, hooks = tools_factory()
        res = run_items(items, cfg, call, out_dir, today, lang, drafter, bool(mail.get("create_drafts", True)), send, bool(getattr(a, "force", False)), hooks)
    except (SendRefused,) as exc:
        emit_err(str(exc))
        return EXIT_REFUSED
    except (DraftError, CalendarError) as exc:
        emit_err(f"Fout: {exc}")
        return EXIT_NET if isinstance(exc, CalendarError) else EXIT_TOOL
    out.emit(res, "\n".join([f"{res['date']}: {len(res['results'])} item(s)"] + [f"  - {r['status']:22} {r['client']}: {r['title']}" + (f" -> {r['files'][0]}" if r.get("files") else "") for r in res["results"]]))
    return EXIT_TOOL if any(r["status"] == "fouten" for r in res["results"]) else EXIT_OK


def _init(a, out) -> int:
    from .cli import EXIT_CONFIG, EXIT_OK
    p = Path(getattr(a, "path", "workflows.toml"))
    if p.exists() and not getattr(a, "force", False):
        sys.stderr.write(f"{p} bestaat al; gebruik --force om te overschrijven.\n")
        return EXIT_CONFIG
    p.write_text(EXAMPLE_CONFIG, encoding="utf-8")
    out.emit({"written": str(p)}, f"Voorbeeldconfiguratie geschreven naar {p}. Pas ze aan en verifieer elke regel bij de officiële bron.")
    return EXIT_OK


EXAMPLE_CONFIG = '''# Voorbeeldconfiguratie voor 'yuki-api-connector workflows'. [Voorbeeld]-gegevens; GEEN geheimen in dit bestand.
# De regels hieronder (vervaldag, maand, voorsprong) zijn een VOORBEELD en geen feit: verifieer actuele regel bij de officiële bron ('source').
# Powered by FISCALCI Accounting & Tax (Askin Alci)
# Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels.
[settings]
timezone = "Europe/Brussels"
days_ahead = 2          # vergaderingen binnen N dagen worden voorbereid
language = "nl"         # nl | en
out_dir = "workflow-output"
max_items = 10          # bescherming van het Yuki-daglimiet per run
overdue_days = 14       # verlopen verplichtingen blijven zo lang in de lijst

[calendar]
adapter = "ics"         # ics | graph | google (graph/google: token uit een omgevingsvariabele; verify current docs)
path = "agenda-voorbeeld.ics"      # relatief aan dit bestand; zet hier uw eigen .ics-export
# url_env = "YUKI_WF_ICS_URL"      # NAAM van een omgevingsvariabele; een privé-ICS-URL zelf nooit in dit bestand

[mail]
adapter = "eml"         # eml | outlook | gmail | agentmail | smtp  (verstuurt NOOIT zonder allow_send + --send + bevestiging per run)
create_drafts = true
allow_send = false      # verzenden naar klanten is uw eigen verantwoordelijkheid
signature = "[Voorbeeld] Uw boekhouder"

[template]              # uw eigen overzicht: kies secties en kerncijfers
sections = ["kpis", "open_items", "missing_documents", "dossier_status"]
kpis = ["omzet", "kosten", "resultaat", "liquide_middelen", "open_debiteuren.vervallen", "open_crediteuren.vervallen", "btw_indicatie"]
compare = true
# export_formats = ["csv", "xlsx"]  # optioneel: schrijft ook een export naar <out_dir>/exports/<klant>

[[clients]]
name = "[Voorbeeld] BV"
administratie = "[Voorbeeld] BV"
match_keywords = ["[Voorbeeld] BV"]
match_domains = ["voorbeeld.example"]
email_to = ["contact@voorbeeld.example"]
status_file = "status-voorbeeld.json"
documents = ["Bankuittreksels van de lopende maand"]
obligations = ["btw-kwartaal", "klantenlisting", "intracommunautaire-listing", "ubo-register", "jaarrekening", "vennootschapsbelasting", "personenbelasting"]

[[obligations]]
id = "btw-maand"
title = "Periodieke btw-aangifte (maandelijks)"
frequency = "monthly"
due_day = 20
due_month_offset = 1
lead_days = 10
verify = "verifieer actuele regel"
source = "https://financien.belgium.be/nl"
checklist = ["Verkoop- en aankoopfacturen van de maand geboekt", "Btw-saldo in Yuki nagekeken", "Aangifte ingediend en betaling gepland"]
documents = ["Ontbrekende aankoopfacturen van de maand"]

[[obligations]]
id = "btw-kwartaal"
title = "Periodieke btw-aangifte (kwartaal)"
frequency = "quarterly"
due_day = 20
due_month_offset = 1
lead_days = 14
verify = "verifieer actuele regel"
source = "https://financien.belgium.be/nl"
checklist = ["Verkoop- en aankoopfacturen van het kwartaal geboekt", "Btw-saldo in Yuki nagekeken", "Aangifte ingediend en betaling gepland"]
documents = ["Ontbrekende aankoopfacturen van het kwartaal"]

[[obligations]]
id = "klantenlisting"
title = "Jaarlijkse klantenlisting"
frequency = "annual"
due_month = 3
due_day = 31
year_offset = -1
lead_days = 30
verify = "verifieer actuele regel"
source = "https://financien.belgium.be/nl"
checklist = ["Btw-nummers van alle klanten gecontroleerd", "Listing opgemaakt en ingediend"]
documents = ["Btw-nummers van nieuwe klanten"]

[[obligations]]
id = "intracommunautaire-listing"
title = "Intracommunautaire listing"
frequency = "monthly"
due_day = 20
due_month_offset = 1
lead_days = 10
verify = "verifieer actuele regel"
source = "https://financien.belgium.be/nl"
checklist = ["Intracommunautaire leveringen en diensten aangeduid", "Listing ingediend"]
documents = ["Facturen aan klanten in andere EU-lidstaten"]

[[obligations]]
id = "ubo-register"
title = "UBO-register: controle en bijwerking"
frequency = "annual"
due_month = 6
due_day = 30
year_offset = 0
lead_days = 30
verify = "verifieer actuele regel (de verplichting hangt aan wijzigingen en jaarlijkse bevestiging; controleer de voorwaarden)"
source = "https://financien.belgium.be/nl"
checklist = ["Uiteindelijk begunstigden gecontroleerd", "Wijzigingen doorgegeven of bevestiging gedaan"]
documents = ["Actueel aandeelhoudersregister"]

[[obligations]]
id = "jaarrekening"
title = "Jaarrekening: afsluiten en neerleggen"
frequency = "annual"
due_month = 7
due_day = 31
year_offset = -1
lead_days = 45
verify = "verifieer actuele regel"
source = "https://www.nbb.be/nl/balanscentrale"
checklist = ["Boekjaar afgesloten in Yuki", "Jaarrekening opgemaakt en goedgekeurd", "Neerlegging voorbereid"]
documents = ["Getekende notulen van de algemene vergadering"]

[[obligations]]
id = "vennootschapsbelasting"
title = "Aangifte vennootschapsbelasting"
frequency = "fixed"
dates = ["2027-10-15"]          # [Voorbeeld]: de datum wijzigt jaarlijks; vul de actuele datum zelf in
year_offset = -2
lead_days = 45
verify = "verifieer actuele regel"
source = "https://financien.belgium.be/nl"
checklist = ["Fiscale aanpassingen bepaald", "Aangifte opgemaakt"]
documents = ["Staat van afschrijvingen en provisies"]

[[obligations]]
id = "personenbelasting"
title = "Aangifte personenbelasting"
frequency = "fixed"
dates = ["2027-07-15"]          # [Voorbeeld]: de datum wijzigt jaarlijks; vul de actuele datum zelf in
year_offset = -1
lead_days = 45
verify = "verifieer actuele regel"
source = "https://financien.belgium.be/nl"
checklist = ["Fiscale fiches en bewijsstukken verzameld", "Aangifte opgemaakt"]
documents = ["Loonfiches", "Bewijsstukken van aftrekbare uitgaven"]
'''
