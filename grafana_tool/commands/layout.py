"""layout: ricalcola i gridPos dei pannelli sulla griglia.

Comando di dashboard, non CRUD: normalizza la disposizione di tutte le
righe oppure di una sola (`--in-row`). Le righe espanse restano espanse e
partono sotto l'intestazione; quelle collassate restano collassate.
"""
from __future__ import annotations

import argparse

from grafana_tool.command_base import WriteCommand
from grafana_tool.model import iter_rows, require_row, row_children


class LayoutCommand(WriteCommand):
    NAME = "layout"
    HELP = "Ricalcola i gridPos dei pannelli"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--in-row", dest="in_row", type=int, metavar="N",
                            help="Limita a una riga specifica")
        parser.add_argument("--columns", type=int, default=24,
                            help="Larghezza griglia (default: 24)")
        parser.add_argument("--default-width", dest="default_width", type=int, default=12,
                            help="Larghezza di default (default: 12)")
        parser.add_argument("--default-height", dest="default_height", type=int, default=8,
                            help="Altezza di default (default: 8)")

    def modify(self, db: dict, args: argparse.Namespace) -> dict:
        if args.columns <= 0:
            raise ValueError("--columns deve essere > 0.")

        if args.in_row is not None:
            rows = [require_row(db, args.in_row)]
        else:
            rows = list(iter_rows(db))

        total = 0
        for row in rows:
            # Le righe espanse tengono i pannelli top-level dopo la riga: vanno
            # reflowati quelli, partendo sotto l'intestazione della riga.
            is_expanded = row.get("collapsed") is False and not (row.get("panels") or [])
            x, y, row_h = 0, 1 if is_expanded else 0, 0
            for panel in row_children(db, row):
                if not isinstance(panel, dict):
                    continue
                grid = panel.get("gridPos") if isinstance(panel.get("gridPos"), dict) else {}
                w = int(grid.get("w") or args.default_width)
                h = int(grid.get("h") or args.default_height)
                if x + w > args.columns and x > 0:
                    x = 0
                    y += row_h
                    row_h = 0
                grid.update({"x": x, "y": y, "w": w, "h": h})
                panel["gridPos"] = grid
                x += w
                row_h = max(row_h, h)
                total += 1
            if is_expanded:
                row_grid = row.get("gridPos")
                if isinstance(row_grid, dict):
                    row_grid["y"] = 0
            else:
                row["collapsed"] = True

        print(f"Layout applicato a {total} pannelli.")
        return db


command = LayoutCommand()
