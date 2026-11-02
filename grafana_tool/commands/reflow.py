"""reflow: normalizza i gridPos (x, y, w, h) dei pannelli."""
from __future__ import annotations

import argparse

from grafana_tool.cli_common import add_write_options
from grafana_tool.io import load_dashboard
from grafana_tool.model import find_row, iter_rows, row_children
from grafana_tool.persist import save_and_validate

NAME = "reflow"
HELP = "Ricalcola gridPos (x, y, w, h) dei pannelli"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--row", type=int, help="Limita a una riga specifica")
    parser.add_argument("--columns", type=int, default=24, help="Larghezza griglia (default: 24)")
    parser.add_argument("--default-width", type=int, default=12, help="Larghezza di default (default: 12)")
    parser.add_argument("--default-height", type=int, default=8, help="Altezza di default (default: 8)")
    add_write_options(parser)

def run(args: argparse.Namespace) -> int:
    if args.columns <= 0:
        raise ValueError("--columns deve essere > 0.")
    db = load_dashboard(args.file)

    if args.row is not None:
        row = find_row(db, args.row)
        if row is None:
            raise ValueError(f"Riga {args.row} non trovata.")
        rows = [row]
    else:
        rows = list(iter_rows(db))

    total = 0
    for r in rows:
        # Le righe espanse tengono i pannelli top-level dopo la riga: vanno
        # reflowati quelli, partendo sotto l'intestazione della riga.
        is_expanded = r.get("collapsed") is False and not (r.get("panels") or [])
        start_y = 1 if is_expanded else 0
        x, y, row_h = 0, start_y, 0
        for p in row_children(db, r):
            if not isinstance(p, dict):
                continue
            gp = p.get("gridPos") if isinstance(p.get("gridPos"), dict) else {}
            w = int(gp.get("w") or args.default_width)
            h = int(gp.get("h") or args.default_height)
            if x + w > args.columns and x > 0:
                x = 0
                y += row_h
                row_h = 0
            gp["x"] = x
            gp["y"] = y
            gp["w"] = w
            gp["h"] = h
            p["gridPos"] = gp
            x += w
            row_h = max(row_h, h)
            total += 1
        if is_expanded:
            rgp = r.get("gridPos")
            if isinstance(rgp, dict):
                rgp["y"] = 0
        else:
            r["collapsed"] = True

    print(f"Reflow applicato a {total} pannelli.")
    return save_and_validate(db, args)
