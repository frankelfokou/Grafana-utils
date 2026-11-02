"""list-rows: elenca le righe della dashboard."""
from __future__ import annotations

import argparse

from grafana_tool.io import load_dashboard
from grafana_tool.model import iter_rows, row_children

NAME = "list-rows"
HELP = "Elenca le righe (id, titolo, numero pannelli, collapsed)"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")

def run(args: argparse.Namespace) -> None:
    db = load_dashboard(args.file)
    rows = list(iter_rows(db))
    if not rows:
        print("Nessuna riga trovata.")
        return
    print(f"{'ID':>6}  {'Titolo':<50}  {'Pannelli':>8}  {'Collapsed':>9}")
    print("-" * 82)
    for r in rows:
        title = r.get("title") or "(senza titolo)"
        n = len(row_children(db, r))
        print(f"{str(r.get('id', '?')):>6}  {title:<50}  {n:>8}  {str(r.get('collapsed', '')):>9}")
