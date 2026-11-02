"""list-panels: elenca i pannelli indicando la riga di appartenenza."""
from __future__ import annotations

import argparse
from typing import Any, Optional

from grafana_tool.io import load_dashboard
from grafana_tool.model import find_row, iter_panels_with_parent

NAME = "list-panels"
HELP = "Elenca i pannelli con la riga di appartenenza"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--row", type=int, help="Limita alla riga con questo ID")

def _owner(row: Optional[dict[str, Any]]) -> str:
    return f"riga {row.get('id', '?')}" if row else "nessuna riga"

def _print_panel(p: dict[str, Any], row: Optional[dict[str, Any]]) -> None:
    pid = p.get("id", "?")
    typ = p.get("type", "?")
    title = p.get("title") or "(senza titolo)"
    print(f"- [{pid}] {typ}: {title}  ({_owner(row)})")
    for t in p.get("targets") or []:
        if isinstance(t, dict) and t.get("expr"):
            expr = t["expr"]
            if len(expr) > 100:
                expr = expr[:97] + "..."
            print(f"    expr: {expr}")

def run(args: argparse.Namespace) -> None:
    db = load_dashboard(args.file)
    items = list(iter_panels_with_parent(db))

    if args.row is not None:
        if find_row(db, args.row) is None:
            raise ValueError(f"Riga {args.row} non trovata.")
        items = [(r, p) for r, p in items if r is not None and r.get("id") == args.row]

    if not items:
        print("Nessun pannello trovato.")
        return

    for row, panel in items:
        _print_panel(panel, row)
