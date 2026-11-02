"""prune: rimuove pannelli per id, tipo o titolo (regex)."""
from __future__ import annotations

import argparse
from typing import Any

from grafana_tool.cli_common import add_write_options
from grafana_tool.io import load_dashboard
from grafana_tool.model import iter_rows, title_regex
from grafana_tool.persist import save_and_validate

NAME = "prune"
HELP = "Rimuove pannelli per --panel-id, --match-title o --match-type"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--panel-id", type=int, action="append", default=[],
                        help="ID pannello da rimuovere (ripetibile)")
    parser.add_argument("--match-title", help="Rimuove pannelli con titolo che matcha regex")
    parser.add_argument("--match-type", help="Rimuove pannelli di un tipo")
    add_write_options(parser)

def _matches(p: dict[str, Any], ids: set[int], title_re, match_type: str | None) -> bool:
    if p.get("id") in ids:
        return True
    if title_re and title_re.search(p.get("title") or ""):
        return True
    if match_type and str(p.get("type") or "").casefold() == match_type.casefold():
        return True
    return False

def run(args: argparse.Namespace) -> int:
    if not (args.panel_id or args.match_title or args.match_type):
        raise ValueError("Specificare --panel-id, --match-title o --match-type.")
    db = load_dashboard(args.file)
    ids = set(args.panel_id)
    title_re = title_regex(args.match_title) if args.match_title else None

    removed = 0

    for r in iter_rows(db):
        before = len(r.get("panels") or [])
        r["panels"] = [
            p for p in r.get("panels") or []
            if not (isinstance(p, dict) and _matches(p, ids, title_re, args.match_type))
        ]
        removed += before - len(r["panels"])

    top = db.get("panels")
    if isinstance(top, list):
        before = len(top)
        db["panels"] = [
            p for p in top
            if not (isinstance(p, dict) and p.get("type") != "row"
                    and _matches(p, ids, title_re, args.match_type))
        ]
        removed += before - len(db["panels"])

    print(f"Pannelli rimossi: {removed}.")
    return save_and_validate(db, args)
