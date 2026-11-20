"""CLI: ``python -m yuki_core get-session | status | list-dossiers [--internal-code] | analyze-dossier``.

``analyze-dossier DOSSIER --boekjaar 2025 [--van … --tot …] [--fiscaal]
[--klasse4 saldo|rubriek] [--output PAD]``: zonder ``--output`` gaat de
``yearly_totals.json`` naar stdout, met ``--output`` alleen naar dat pad.

Leest YUKI_ACCESS_KEY / YUKI_CACHE_KEY uit de omgeving. Toont nooit de
volledige access key of session ID.
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from . import tools
from .errors import YukiDailyLimitReached, YukiError


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="yuki_core", description="Read-only Yuki-client")
    p.add_argument("-v", "--verbose", action="store_true")
    sub = p.add_subparsers(dest="cmd", required=True)
    sub.add_parser("get-session", help="Controleer/haal een sessie (gecachet)")
    st = sub.add_parser("status", help="Dagteller per domein + cachegrootte (geen Yuki-call)")
    st.add_argument("--json", action="store_true")
    ld = sub.add_parser("list-dossiers", help="Toon administraties (naam + ID)")
    ld.add_argument("--internal-code", action="store_true", help="AdministrationsWithInternalCustomerCode")
    ad = sub.add_parser("analyze-dossier", help="Jaartotalen + ratio's (yearly_totals.json)")
    ad.add_argument("dossier", help="Administration ID of (deel van de) naam")
    ad.add_argument("--boekjaar", help="Jaartal; standaard 1/1 – 31/12")
    ad.add_argument("--van", help="Begindatum (YYYY-MM-DD), bv. gebroken boekjaar")
    ad.add_argument("--tot", help="Einddatum (YYYY-MM-DD)")
    ad.add_argument("--fiscaal", action="store_true", help="financialMode 1 (fiscaal); standaard 0 (commercieel)")
    ad.add_argument("--klasse4", choices=("saldo", "rubriek"), default="saldo",
                    help="Klasse 4 indelen op saldo (standaard) of op MAR-rubriek")
    ad.add_argument("--output", help="Schrijf yearly_totals.json naar dit pad (bestand of map)")
    args = p.parse_args(argv)
    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")
    if args.cmd == "status":
        from .status import main as status_main
        return status_main(["--json"] if args.json else [])
    try:
        if args.cmd == "get-session":
            s = tools.yuki_get_session()
            print(f"session ok, expires {s['expires_at']} (key {s['key_fingerprint']}…, "
                  f"scope {s['scope']}, calls vandaag {s['calls_today']})")
        elif args.cmd == "list-dossiers":
            for a in tools.yuki_list_dossiers(with_internal_code=args.internal_code):
                extra = f"\t{a['internal_customer_code']}" if a.get("internal_customer_code") else ""
                print(f"{a['id']}\t{a['name']}{extra}")
        elif args.cmd == "analyze-dossier":
            res = tools.yuki_analyze_dossier(args.boekjaar, van=args.van, tot=args.tot,
                                             financial_mode=1 if args.fiscaal else 0,
                                             naam_of_id=args.dossier, klasse4=args.klasse4,
                                             output_path=args.output)
            if args.output:
                bal = "ok" if res["controle"]["in_evenwicht"] else "NIET in evenwicht"
                print(f"yearly_totals.json geschreven naar {args.output} "
                      f"(boekjaar {res['boekjaar']['van']} – {res['boekjaar']['tot']}, "
                      f"{res['financial_mode_label']}, balans {bal})")
            else:
                print(json.dumps(res, indent=2, ensure_ascii=False))
    except YukiDailyLimitReached as exc:
        print(f"daglimiet bereikt: {exc}", file=sys.stderr)
        return 3
    except (YukiError, ValueError) as exc:
        print(f"fout: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
