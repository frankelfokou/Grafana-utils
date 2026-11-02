"""move: sposta righe o pannelli.

Le due operazioni hanno la stessa forma (selettori + destinazione):

  - `panel` — `--to-row N` sceglie la riga di destinazione, `--position`
    sceglie cima o fondo del suo blocco;
  - `row` — `--before`/`--after` oppure `--position top|bottom` scelgono la
    posizione tra le righe della dashboard.
"""
from __future__ import annotations

import argparse

from grafana_tool import objects
from grafana_tool.cli_common import add_kind_argument, add_selectors
from grafana_tool.command_base import WriteCommand

VERB = {objects.ROW: "spostata", objects.PANEL: "spostato"}


class MoveCommand(WriteCommand):
    NAME = "move"
    HELP = "Sposta righe o pannelli"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_kind_argument(parser)
        add_selectors(parser)
        parser.add_argument(
            "--to-row", dest="to_row", type=int, metavar="N",
            help="Riga di destinazione (obbligatorio per i pannelli)",
        )
        parser.add_argument(
            "--before", type=int, metavar="N",
            help="Posiziona prima dell'oggetto con questo id",
        )
        parser.add_argument(
            "--after", type=int, metavar="N",
            help="Posiziona dopo l'oggetto con questo id",
        )
        parser.add_argument(
            "--position", choices=["top", "bottom"], default="bottom",
            help="In cima o in fondo al contenitore di destinazione (default: bottom)",
        )

    @staticmethod
    def _row_destination(args: argparse.Namespace) -> str:
        if args.before is not None:
            return f"prima dell'oggetto {args.before}"
        if args.after is not None:
            return f"dopo l'oggetto {args.after}"
        return "in cima" if args.position == "top" else "in fondo"

    def modify(self, db: dict, args: argparse.Namespace) -> dict:
        objects.require_selector(
            args.kind,
            ids=args.id,
            match_title=args.match_title,
            match_type=args.match_type,
            in_row=args.in_row,
        )
        if args.to_row is not None and (args.before is not None or args.after is not None):
            raise ValueError("Usare --to-row oppure --before/--after, non entrambi.")
        if args.kind == objects.ROW and args.to_row is not None:
            raise ValueError("--to-row vale solo per i pannelli.")
        if args.kind == objects.PANEL and args.to_row is None and args.before is None and args.after is None:
            raise ValueError(
                "Indicare la destinazione: --to-row N oppure --before/--after N."
            )

        targets = objects.select_targets(
            db, args.kind,
            ids=args.id,
            match_title=args.match_title,
            match_type=args.match_type,
            in_row=args.in_row,
        )
        if not targets:
            raise ValueError(
                f"Nessun {objects.NOUN[args.kind]} corrisponde ai selettori indicati."
            )

        for target in targets:
            if args.kind == objects.ROW:
                objects.move_row(
                    db, target, before=args.before, after=args.after,
                    position=args.position,
                )
                print(f"{target.label()} {VERB[objects.ROW]} {self._row_destination(args)}.")
            elif args.to_row is not None:
                objects.move_panel(db, target, args.to_row, position=args.position)
                print(f"{target.label()} {VERB[objects.PANEL]} nella riga {args.to_row}.")
            else:
                objects.move_panel_relative(
                    db, target, args.before if args.before is not None else args.after,
                    after=args.after is not None,
                )
                print(f"{target.label()} {VERB[objects.PANEL]} {self._row_destination(args)}.")

        noun = objects.PLURAL[args.kind].capitalize()
        print(f"{noun} spostate/i: {len(targets)}.")
        return db


command = MoveCommand()
