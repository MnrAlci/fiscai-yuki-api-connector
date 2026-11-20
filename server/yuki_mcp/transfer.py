"""Dossieroverdracht per boekjaar (voor de volgende boekhouder/confrater). Alleen lezen voor Yuki; schrijft lokale bestanden.

Per boekjaar een map met: rekeningschema, proefbalans (slot, jaarafsluiting, begin), startbalans (API), grootboekmutaties,
openstaande debiteuren/crediteuren op balansdatum, contacten, btw-aangiften en btw-codes (indien beschikbaar), saldi van klasse 2
(vaste activa: indicatie, geen activaregister), en met ``inclusief_documenten`` de documentMETADATA van het archief. Daarnaast
MANIFEST.json (bestanden, rijen, SHA-256) en CONTROL.md (afstemmingen). Hervatten via een checkpoint. Zie docs/DOSSIER-TRANSFER.md.

Beperkingen van de Yuki-API (verifieer actuele regel): geen lijst van boekjaren, geen dagboekcode in de mutaties, geen activaregister,
geen bestandsinhoud van documenten via de toegelaten leesmethodes. Dat staat ook in het README voor de ontvanger.
"""
from __future__ import annotations

import csv
import hashlib
import json
import zipfile
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Callable, Optional

ATTR = "Powered by FISCALCI Accounting & Tax (Askin Alci)"
BE_NL = "Bedoeld voor Belgische boekhouders/accountants; gebaseerd op Belgische boekhoud- en btw-regels (MAR, Belgisch btw-stelsel). Gebruik buiten België: verifieer zelf de lokale regels."
THRESHOLD = 150
MAX_YEARS = 15
TOOLS_USED = ("yuki_rekeningschema", "yuki_proefbalans", "yuki_startbalans", "yuki_grootboekmutaties", "yuki_openstaande_posten", "yuki_klanten_leveranciers",
              "yuki_btw_aangiftes", "yuki_btw_codes", "yuki_archief_documenten", "yuki_status")
CHECKPOINT = ".transfer-checkpoint.json"


class TransferError(Exception):
    pass


def D(v: Any) -> Decimal:
    try:
        return Decimal(str(v)) if v not in (None, "") else Decimal(0)
    except InvalidOperation:
        return Decimal(0)


def rows_from(res: Any) -> list[dict]:
    if isinstance(res, dict):
        for k in ("gegevens", "rows", "items"):
            if isinstance(res.get(k), list):
                return [r if isinstance(r, dict) else {"waarde": r} for r in res[k]]
        return [res]
    if isinstance(res, list):
        return [r if isinstance(r, dict) else {"waarde": r} for r in res]
    return []


def year_bounds(year: int, start_month: int = 1) -> tuple[date, date]:
    s = date(year, start_month, 1)
    e = date(year + 1, start_month, 1) - timedelta(days=1)   # start_month=1: 31 december
    return s, e


def sha256(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for chunk in iter(lambda: fh.read(65536), b""):
            h.update(chunk)
    return h.hexdigest()


def _cols(rows: list[dict]) -> list[str]:
    out: list[str] = []
    for r in rows:
        for k in r:
            if k not in out:
                out.append(k)
    return out


def _cell(v: Any) -> Any:
    if isinstance(v, (dict, list)):
        return json.dumps(v, ensure_ascii=False)
    return "" if v is None else v


def write_csv(p: Path, rows: list[dict]) -> None:
    cols = _cols(rows) or ["leeg"]
    with open(p, "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols)
        for r in rows:
            w.writerow([_cell(r.get(c)) for c in cols])


def write_xlsx(p: Path, rows: list[dict]) -> None:
    """Minimale xlsx (inline strings, geen extra pakketten). Getallen blijven tekst: exact zoals Yuki ze gaf."""
    from xml.sax.saxutils import escape
    cols = _cols(rows) or ["leeg"]

    def ref(i: int) -> str:
        s = ""
        i += 1
        while i:
            i, r = divmod(i - 1, 26)
            s = chr(65 + r) + s
        return s
    data = [cols] + [[_cell(r.get(c)) for c in cols] for r in rows]
    body = "".join(f'<row r="{ri}">' + "".join(f'<c r="{ref(ci)}{ri}" t="inlineStr"><is><t xml:space="preserve">{escape(str(v))}</t></is></c>' for ci, v in enumerate(row)) + "</row>"
                   for ri, row in enumerate(data, 1))
    parts = {
        "[Content_Types].xml": '<?xml version="1.0" encoding="UTF-8"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types"><Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/><Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/><Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
        "_rels/.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/></Relationships>',
        "xl/workbook.xml": '<?xml version="1.0" encoding="UTF-8"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships"><sheets><sheet name="Data" sheetId="1" r:id="rId1"/></sheets></workbook>',
        "xl/_rels/workbook.xml.rels": '<?xml version="1.0" encoding="UTF-8"?><Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships"><Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet1.xml"/></Relationships>',
        "xl/worksheets/sheet1.xml": f'<?xml version="1.0" encoding="UTF-8"?><worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>{body}</sheetData></worksheet>',
    }
    with zipfile.ZipFile(p, "w", zipfile.ZIP_DEFLATED) as z:
        for n, t in parts.items():
            z.writestr(zipfile.ZipInfo(n, (2026, 1, 1, 0, 0, 0)), t)


# ------------------------------------------------------------------ schatting
def estimate(chart_rows: int, years: int, all_accounts: bool, documents: bool, remaining: Optional[int]) -> dict:
    """Bovengrens van het aantal tool-aanroepen (elk is één SOAP-call, plus hoogstens één aanmeldcall per sessie)."""
    # proefbalans x3, startbalans, open posten x2, btw (codes + aangiften) x2, documenten ~3 pagina's
    per_year_fixed = 3 + 1 + 2 + 2 + (3 if documents else 0)
    entries = chart_rows                                          # bovengrens: één call per rekening (standaard alleen rekeningen met saldo)
    total = 1 + years * (per_year_fixed + entries) + 3            # schema (1) + per jaar + contacten (~3 pagina's)
    return {"max_calls": total, "years": years, "per_year_fixed": per_year_fixed, "accounts_upper_bound": entries, "remaining_today": remaining,
            "exceeds_remaining": remaining is not None and total > remaining,
            "note": "Bovengrens. Standaard worden alleen rekeningen met een saldo aan begin of einde van het jaar opgehaald; het werkelijke aantal ligt meestal lager."}


# ------------------------------------------------------------------ uitvoeren
class Checkpoint:
    def __init__(self, root: Path, params: dict, resume: bool) -> None:
        self.path = root / CHECKPOINT
        self.data: dict = {"params": params, "steps": {}}
        if resume and self.path.is_file():
            old = json.loads(self.path.read_text(encoding="utf-8"))
            if old.get("params") != params:
                raise TransferError("Het checkpoint in deze map hoort bij andere instellingen (administratie, jaren of opties). Gebruik een andere map of verwijder het checkpoint.")
            self.data = old

    def done(self, key: str, root: Path) -> bool:
        s = self.data["steps"].get(key)
        if not s or s.get("failed"):
            return False
        return (root / s["file"]).is_file() if s.get("file") else True

    def mark(self, key: str, **info: Any) -> None:
        self.data["steps"][key] = info
        self.path.write_text(json.dumps(self.data, ensure_ascii=False, indent=2), encoding="utf-8")


def _save(folder: Path, name: str, rows: list[dict], formats: list[str]) -> list[str]:
    folder.mkdir(parents=True, exist_ok=True)
    out = []
    for f in formats:
        p = folder / f"{name}.{f}"
        if f == "csv":
            write_csv(p, rows)
        elif f == "json":
            p.write_text(json.dumps({"dataset": name, "rows": rows}, ensure_ascii=False, indent=1, default=str), encoding="utf-8")
        elif f == "xlsx":
            write_xlsx(p, rows)
        out.append(p.name)
    return out


def _load(folder: Path, name: str) -> Optional[list[dict]]:
    p = folder / f"{name}.json"
    return json.loads(p.read_text(encoding="utf-8"))["rows"] if p.is_file() else None


def _limit_hit(exc: Exception) -> bool:
    return type(exc).__name__ == "YukiDailyLimitReached"


def run_export(call: Callable[[str, dict], Any], *, administratie: str, years: list[int], out: Path, domein: Optional[str] = None, zip_years: bool = False,
               include_documents: bool = False, all_accounts: bool = False, start_month: int = 1, formats: Optional[list[str]] = None, resume: bool = True,
               threshold: int = THRESHOLD, confirmed: bool = False, estimate_only: bool = False, debtor_prefix: str = "40", creditor_prefix: str = "44",
               now: Optional[datetime] = None) -> dict:
    formats = formats or ["csv", "json"]
    if not years or len(years) > MAX_YEARS or any(y < 1990 or y > 2100 for y in years):
        raise TransferError(f"Geef 1 tot {MAX_YEARS} boekjaren (jaartallen 1990 tot 2100).")
    if not 1 <= start_month <= 12:
        raise TransferError("fy_start_month moet 1 tot 12 zijn.")
    years = sorted(set(years))
    base = {"administratie": administratie, **({"domein": domein} if domein else {})}
    # --- schatting (1 call: rekeningschema) en quota
    chart_res = call("yuki_rekeningschema", dict(base))
    chart = rows_from(chart_res)
    remaining = None
    try:
        st = call("yuki_status", {})
        doms = [d for d in st.get("domains", []) if d.get("remaining") is not None]
        remaining = min((d["remaining"] for d in doms), default=None) if doms else st.get("limit")
    except Exception:  # noqa: BLE001 - schatting blijft bruikbaar zonder statusinfo
        pass
    est = estimate(len(chart), len(years), all_accounts, include_documents, remaining)
    need_confirm = est["max_calls"] > threshold or est["exceeds_remaining"]
    res: dict[str, Any] = {"estimate": est, "threshold": threshold, "needs_confirmation": need_confirm and not confirmed, "years": years, "out": str(out), "read_only": True}
    if estimate_only or (need_confirm and not confirmed):
        res["status"] = "schatting" if estimate_only else "bevestiging_nodig"
        return res
    out.mkdir(parents=True, exist_ok=True)
    params = {"administratie": administratie, "domein": domein, "years": years, "docs": include_documents, "all_accounts": all_accounts, "start_month": start_month, "formats": formats}
    cp = Checkpoint(out, params, resume)
    interrupted: Optional[str] = None
    summaries: list[dict] = []
    contacts_cache: Optional[list[dict]] = None

    def step(key: str, folder: Path, name: str, fn: Callable[[], list[dict]]) -> Optional[list[dict]]:
        nonlocal interrupted
        if interrupted:
            return None
        if cp.done(key, out):
            return _load(folder, name) if (folder / f"{name}.json").is_file() else []
        try:
            rows = fn()
        except Exception as exc:  # noqa: BLE001
            if _limit_hit(exc):
                interrupted = f"daglimiet bereikt bij {key}; start dezelfde opdracht opnieuw om te hervatten"
                return None
            from .convert import scrub
            cp.mark(key, error=scrub(f"{type(exc).__name__}: {exc}"), file=None)
            cp.data["steps"][key]["failed"] = True
            return None
        files = _save(folder, name, rows, formats)
        cp.mark(key, rows=len(rows), file=str((folder / files[0]).relative_to(out)))
        return rows

    for y in years:
        s, e = year_bounds(y, start_month)
        fy = out / str(y)
        fy.mkdir(parents=True, exist_ok=True)
        a = lambda **kw: {**base, **kw}  # noqa: E731
        step(f"{y}:chart", fy, "rekeningschema", lambda: chart)
        tb_close = step(f"{y}:tb_close", fy, "proefbalans-slot", lambda: rows_from(call("yuki_proefbalans", a(datum=e.isoformat(), soort="commercieel"))))
        step(f"{y}:tb_yearend", fy, "proefbalans-jaarafsluiting", lambda: rows_from(call("yuki_proefbalans", a(datum=e.isoformat(), soort="jaarafsluiting"))))
        tb_open = step(f"{y}:tb_open", fy, "proefbalans-begin", lambda: rows_from(call("yuki_proefbalans", a(datum=(s - timedelta(days=1)).isoformat(), soort="commercieel"))))
        step(f"{y}:startbalans", fy, "startbalans-api", lambda: rows_from(call("yuki_startbalans", a(boekjaar=y, financieel_modus=0))))
        for soort in ("debiteuren", "crediteuren"):
            step(f"{y}:open_{soort}", fy, f"openstaande-{soort}-einde", lambda soort=soort: rows_from(call("yuki_openstaande_posten", a(soort=soort, peildatum=e.isoformat()))))
        step(f"{y}:vat", fy, "btw-aangiften", lambda: rows_from(call("yuki_btw_aangiftes", a(jaar=y))))
        step(f"{y}:vatcodes", fy, "btw-codes", lambda: rows_from(call("yuki_btw_codes", a())))
        if contacts_cache is None and not interrupted:
            contacts_cache = step(f"{y}:contacts", fy, "contacten", lambda: rows_from(call("yuki_klanten_leveranciers", a(zoekoptie="All", contacttype="Both", actief="Both"))))
        elif contacts_cache is not None:
            step(f"{y}:contacts", fy, "contacten", lambda: contacts_cache or [])
        else:
            pass
        step(f"{y}:fixed", fy, "klasse-2-saldi-indicatie", lambda: [r for r in (tb_close or []) if str(r.get("code", "")).startswith("2")])
        if include_documents:
            step(f"{y}:docs", fy, "archief-documenten-metadata", lambda: rows_from(call("yuki_archief_documenten", a(van=s.isoformat(), tot=e.isoformat()))))
        # grootboekmutaties per rekening (met checkpoint per rekening)
        codes: list[str] = []
        seen = set()
        for r in (tb_close or []) + (tb_open or []):
            c = str(r.get("code") or "")
            if c and c not in seen and (all_accounts or D(r.get("balance")) != 0 or D(r.get("debit")) != 0 or D(r.get("credit")) != 0):
                seen.add(c)
                codes.append(c)
        if all_accounts:
            for r in chart:
                c = str(r.get("code") or "")
                if c and c not in seen:
                    seen.add(c)
                    codes.append(c)
        parts = fy / "_delen"
        entries_done = cp.done(f"{y}:entries", out)
        if not entries_done and not interrupted and tb_close is not None:
            for c in sorted(codes):
                key = f"{y}:entries:{c}"
                if cp.done(key, out):
                    continue
                part = parts / f"{c}.json"
                try:
                    rows = rows_from(call("yuki_grootboekmutaties", a(rekening=c, van=s.isoformat(), tot=e.isoformat())))
                except Exception as exc:  # noqa: BLE001
                    if _limit_hit(exc):
                        interrupted = f"daglimiet bereikt bij rekening {c} ({y}); start dezelfde opdracht opnieuw om te hervatten"
                        break
                    from .convert import scrub
                    cp.mark(key, error=scrub(f"{type(exc).__name__}: {exc}"), file=None)
                    cp.data["steps"][key]["failed"] = True
                    continue
                parts.mkdir(exist_ok=True)
                part.write_text(json.dumps(rows, ensure_ascii=False, default=str), encoding="utf-8")
                cp.mark(key, rows=len(rows), file=str(part.relative_to(out)))
            if not interrupted:
                allrows: list[dict] = []
                for c in sorted(codes):
                    pth = parts / f"{c}.json"
                    if pth.is_file():
                        allrows += [{"rekening": c, **r} if "gl_account_code" not in r else r for r in json.loads(pth.read_text(encoding="utf-8"))]
                names = _save(fy, "grootboekmutaties", allrows, formats)
                journals = _split_journals(fy, allrows, formats)
                cp.mark(f"{y}:entries", rows=len(allrows), file=str((fy / names[0]).relative_to(out)), journals=journals)
                for pth in parts.glob("*.json"):
                    pth.unlink()
                try:
                    parts.rmdir()
                except OSError:
                    pass
                for k in [k for k in cp.data["steps"] if k.startswith(f"{y}:entries:")]:
                    del cp.data["steps"][k]
                cp.mark(f"{y}:entries", **cp.data["steps"][f"{y}:entries"])
        summaries.append({"year": y, "folder": str(fy)})
    failed = sorted(k for k, v in cp.data["steps"].items() if v.get("failed"))
    if not interrupted:
        for sm in summaries:
            y = sm["year"]
            fy = out / str(y)
            ctrl = write_control(fy, y, out, start_month, debtor_prefix, creditor_prefix, bool(cp.data["steps"].get(f"{y}:entries")), all_accounts)
            write_manifest(fy, y, administratie, start_month, include_documents, failed, ctrl)
            sm["control"] = ctrl["summary"]
            if zip_years:
                sm["zip"] = zip_year(out, y)
        write_readme(out, administratie, years, start_month, include_documents, formats)
    res.update({"status": "onderbroken" if interrupted else "klaar", "interrupted": interrupted, "failed_steps": failed, "summaries": summaries, "checkpoint": str(out / CHECKPOINT)})
    return res


def _split_journals(fy: Path, rows: list[dict], formats: list[str]) -> Optional[list[str]]:
    key = next((k for r in rows[:50] for k in r if any(t in k.lower() for t in ("journal", "dagboek"))), None)
    if not key:
        return None
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(str(r.get(key) or "onbekend"), []).append(r)
    for j, rs in groups.items():
        safe = "".join(ch if ch.isalnum() or ch in "-_" else "-" for ch in j)[:40]
        _save(fy / "dagboeken", safe, rs, formats)
    return sorted(groups)


# ------------------------------------------------------------------ controle, manifest, readme, zip
def write_control(fy: Path, year: int, root: Path, start_month: int, dpref: str, cpref: str, has_entries: bool, all_accounts: bool) -> dict:
    tol = Decimal("0.01")
    L = [f"# Controle boekjaar {year}", "", "Automatische afstemmingen op de opgehaalde gegevens. Een afwijking is een vraag, geen conclusie: laat ze nakijken door de boekhouder. Tekenconventie: saldo = debet min credit (verifieer actuele regel bij Yuki).", ""]
    results: list[dict] = []

    def add(name: str, status: str, detail: str) -> None:
        results.append({"check": name, "status": status})
        L.append(f"- **{name}**: {status}. {detail}")
    close, open_, entries = _load(fy, "proefbalans-slot"), _load(fy, "proefbalans-begin"), _load(fy, "grootboekmutaties")
    if close is None:
        add("Proefbalans slot", "niet beschikbaar", "bestand ontbreekt (stap mislukt of onderbroken).")
    else:
        tot = sum((D(r.get("balance")) for r in close), Decimal(0))
        add("Proefbalans slot: som van alle saldi = 0", "OK" if abs(tot) <= tol else "AFWIJKING", f"som = {tot:.2f} over {len(close)} rekeningen.")
    if close is not None and entries is not None:
        bal = {str(r.get("code")): D(r.get("balance")) for r in close}
        opn = {str(r.get("code")): D(r.get("balance")) for r in (open_ or [])}
        sums: dict[str, Decimal] = {}
        for r in entries:
            c = str(r.get("gl_account_code") or r.get("rekening") or "")
            sums[c] = sums.get(c, Decimal(0)) + D(r.get("amount"))
        diffs, ok, na = [], 0, 0
        for c, b in sorted(bal.items()):
            if c not in sums and b == 0 and opn.get(c, Decimal(0)) == 0:
                continue
            expected = b - (opn.get(c, Decimal(0)) if c[:1] in "012345" else Decimal(0))   # balansrekeningen: begin + mutaties = slot; resultaat: mutaties = slot
            if c not in sums:
                if expected == 0 and has_entries:
                    ok += 1                      # rekening zonder mutaties en zonder verschuiving
                else:
                    na += 1
                continue
            if abs(sums[c] - expected) <= tol:
                ok += 1
            else:
                diffs.append((c, sums[c], expected))
        add("Begin + mutaties = slot per rekening", "OK" if not diffs and not na else ("AFWIJKING" if diffs else "GEDEELTELIJK"),
            f"{ok} rekeningen sluiten aan, {len(diffs)} afwijkend, {na} niet opgehaald." + (" Afwijkingen: " + "; ".join(f"{c} mutaties {s:.2f} verwacht {x:.2f}" for c, s, x in diffs[:15]) if diffs else ""))
        total_entries = sum(sums.values(), Decimal(0))
        add("Som van alle mutaties = 0 (dubbel boekhouden)", ("OK" if abs(total_entries) <= tol else "AFWIJKING") if all_accounts else ("OK (gedeeltelijk)" if abs(total_entries) <= tol else "GEDEELTELIJK"),
            f"som = {total_entries:.2f}" + ("" if all_accounts else "; niet alle rekeningen zijn opgehaald (standaard alleen rekeningen met saldo): gebruik --all-accounts voor een volledige test."))
    elif entries is None:
        add("Begin + mutaties = slot", "niet beschikbaar", "grootboekmutaties ontbreken (stap onderbroken of mislukt).")
    prev = root / str(year - 1)
    pv = _load(prev, "proefbalans-jaarafsluiting")
    if open_ is not None and pv is not None:
        a = {str(r.get("code")): D(r.get("balance")) for r in open_ if str(r.get("code", ""))[:1] in "012345"}
        b = {str(r.get("code")): D(r.get("balance")) for r in pv if str(r.get("code", ""))[:1] in "012345"}
        bad = [(c, a.get(c, Decimal(0)), b.get(c, Decimal(0))) for c in sorted(set(a) | set(b)) if abs(a.get(c, Decimal(0)) - b.get(c, Decimal(0))) > tol]
        add(f"Beginbalans {year} = slotbalans {year - 1} (balansrekeningen)", "OK" if not bad else "AFWIJKING",
            f"{len(set(a) | set(b))} rekeningen vergeleken." + (" Afwijkingen: " + "; ".join(f"{c} begin {x:.2f} vs slot vorig jaar {z:.2f}" for c, x, z in bad[:15]) + ". Mogelijke oorzaak: resultaatverwerking of afsluitboekingen." if bad else ""))
    else:
        add(f"Beginbalans {year} = slotbalans {year - 1}", "niet gecontroleerd", f"jaar {year - 1} is niet in deze map geëxporteerd (of onvolledig).")
    for soort, pref, sign in (("debiteuren", dpref, 1), ("crediteuren", cpref, -1)):
        items = _load(fy, f"openstaande-{soort}-einde")
        if items is None or close is None:
            add(f"Openstaande {soort} = saldo rekeningen {pref}*", "niet beschikbaar", "gegevens ontbreken.")
            continue
        s_items = sum((D(r.get("open_amount")) for r in items), Decimal(0))
        s_bal = sign * sum((D(r.get("balance")) for r in close if str(r.get("code", "")).startswith(pref)), Decimal(0))
        add(f"Openstaande {soort} = saldo rekeningen {pref}*", "OK" if abs(s_items - s_bal) <= tol else "AFWIJKING (indicatie)",
            f"posten {s_items:.2f} versus saldo {s_bal:.2f} (verschil {s_items - s_bal:.2f}). Rekeningen buiten {pref}* (bv. voorschotten) of een andere tekenconventie kunnen een verschil verklaren.")
    L += ["", ATTR, "", f"_{BE_NL}_", ""]
    (fy / "CONTROL.md").write_text("\n".join(L), encoding="utf-8")
    bad_n = sum(1 for r in results if r["status"].startswith("AFWIJKING"))
    return {"summary": {"checks": len(results), "afwijkingen": bad_n, "niet_beschikbaar": sum(1 for r in results if r["status"].startswith(("niet", "GEDEELTELIJK")))}, "results": results}


def write_manifest(fy: Path, year: int, administratie: str, start_month: int, docs: bool, failed: list[str], ctrl: dict, now: Optional[datetime] = None) -> None:
    files = []
    for p in sorted(fy.rglob("*")):
        if p.is_file() and p.name != "MANIFEST.json":
            rows = None
            if p.suffix == ".csv":
                with open(p, encoding="utf-8", newline="") as fh:
                    rows = max(sum(1 for _ in csv.reader(fh)) - 1, 0)
            elif p.suffix == ".json" and p.name != "MANIFEST.json":
                try:
                    rows = len(json.loads(p.read_text(encoding="utf-8")).get("rows", []))
                except (ValueError, AttributeError):
                    rows = None
            files.append({"file": p.relative_to(fy).as_posix(), "bytes": p.stat().st_size, "rows": rows, "sha256": sha256(p)})
    s, e = year_bounds(year, start_month)
    m = {"generator": "yuki_dossier_transfer_export", "created_utc": (now or datetime.now(timezone.utc)).isoformat(timespec="seconds"), "administration": administratie,
         "fiscal_year": year, "period": {"from": s.isoformat(), "to": e.isoformat()}, "documents_metadata_included": docs, "read_only": True,
         "failed_steps": [k for k in failed if k.startswith(f"{year}:")], "control_summary": ctrl["summary"], "files": files,
         "notes": ["Rows of CSV files exclude the header. SHA-256 is of the file bytes.", "Document contents are not exported (not available through the read-only allow-list); metadata only."]}
    (fy / "MANIFEST.json").write_text(json.dumps(m, ensure_ascii=False, indent=2), encoding="utf-8")


def zip_year(root: Path, year: int) -> str:
    z = root / f"{year}.zip"
    with zipfile.ZipFile(z, "w", zipfile.ZIP_DEFLATED) as zf:
        for p in sorted((root / str(year)).rglob("*")):
            if p.is_file():
                zf.write(p, f"{year}/{p.relative_to(root / str(year)).as_posix()}")
    return z.name


README = """# Dossieroverdracht: {adm}

Boekjaren: {years} (periode per boekjaar: zie `MANIFEST.json`; boekjaar begint in maand {sm}).

{be}

## Voor de ontvangende boekhouder
Dit pakket is automatisch samengesteld met alleen-lezen toegang tot Yuki. Per boekjaar vindt u een map met:

| Bestand | Inhoud |
|---|---|
| `rekeningschema` | Grootboekrekeningen zoals Yuki ze geeft (Belgisch MAR/PCMN-rekeningstelsel: de codes worden **niet** hernummerd of omgezet; een eventuele mapping naar uw eigen rekeningschema doet u zelf) |
| `proefbalans-slot` / `-begin` / `-jaarafsluiting` | Saldi per rekening op einde, begin en na afsluiting van het boekjaar (saldo = debet min credit) |
| `startbalans-api` | Beginsaldi zoals Yuki ze via de startbalansmethode geeft |
| `grootboekmutaties` | Alle boekingslijnen per rekening (standaard alleen rekeningen met saldo of beweging) |
| `openstaande-debiteuren-einde`, `openstaande-crediteuren-einde` | Openstaande posten op de balansdatum |
| `contacten`, `btw-aangiften`, `btw-codes` | Relaties en btw-gegevens voor zover de API ze levert |
| `klasse-2-saldi-indicatie` | Saldi van klasse 2: een indicatie, **geen activaregister** (dat levert de API niet) |
| `archief-documenten-metadata` | Alleen met `--include-documents`: metadata, geen bestandsinhoud |
| `CONTROL.md` | Afstemmingen (proefbalans, begin = slot vorig jaar, begin + mutaties = slot, openstaande posten) |
| `MANIFEST.json` | Bestanden met rijen en SHA-256 om de integriteit te controleren |

Formaten: {formats}. CSV is UTF-8 met komma als scheidingsteken en punt als decimaalteken; Excel in een Belgische instelling vraagt soms om de importwizard. xlsx bevat alles als tekst, exact zoals Yuki het gaf. JSON bevat `rows`.

## Beperkingen van de Yuki-API (verifieer actuele regel)
- Geen lijst van boekjaren: de jaren zijn opgegeven door de afzender.
- De mutaties bevatten geen dagboekcode; een opdeling per dagboek is daarom alleen aanwezig als Yuki een dagboekveld meegeeft.
- Geen activaregister, geen afschrijvingstabellen, geen bestandsinhoud van documenten via de toegelaten leesmethodes.
- Het dagelijkse aantal calls is begrensd; een onderbroken export kan hervat worden.

## Professionele en wettelijke punten
Dit pakket is een technische hulp, geen juridisch advies en geen vervanging van de overdracht tussen beroepsbeoefenaars.
- **Deontologie**: volg de regels van uw beroepsinstituut voor de overdracht van een dossier (bv. IBR/ITAA/BIBF), de communicatie met de confrater en de opzegging van de opdracht. Verifieer de actuele regels bij het instituut.
- **Klant en toestemming**: zorg dat de klant op de hoogte is en dat u een rechtsgrond heeft voor de overdracht; de klant blijft de eigenaar van zijn gegevens.
- **GDPR**: het pakket bevat persoonsgegevens (relaties, mogelijk documenten). Beperk de verspreiding, bewaar het versleuteld en verwijder kopieën die u niet meer nodig heeft. Zie de Gegevensbeschermingsautoriteit: https://www.gegevensbeschermingsautoriteit.be
- **Veilig overmaken**: gebruik een versleutelde zip of een beveiligd platform, deel het wachtwoord via een ander kanaal en deel de SHA-256 uit `MANIFEST.json` apart.
- **Bewaartermijnen**: de wettelijke bewaartermijn voor boekhoudkundige stukken geldt ook voor wie het dossier overdraagt; verifieer de actuele regel bij de FOD Economie of de FOD Financiën: https://financien.belgium.be/nl

{attr}
"""


def write_readme(out: Path, adm: str, years: list[int], sm: int, docs: bool, formats: list[str]) -> None:
    (out / "README.md").write_text(README.format(adm=adm, years=", ".join(map(str, years)), sm=sm, be=BE_NL, formats=", ".join(formats), attr=ATTR), encoding="utf-8")
