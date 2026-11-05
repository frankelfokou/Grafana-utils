"""move: sposta tab, righe o pannelli.

Le tre operazioni hanno la stessa forma (selettori + destinazione):

  - `tab` — `--before`/`--after` oppure `--position top|bottom` scelgono la
    posizione tra i tab;
  - `row` — `--to-tab` cambia tab, `--before`/`--after`/`--position`
    riordinano tra le righe;
  - `panel` — `--to-row` sceglie la riga di destinazione, `--position`
    sceglie cima o fondo del suo blocco.
"""
from __future__ import annotations

import argparse

from grafana_tool import objects
from grafana_tool.cli_common import add_kind_argument, add_selectors, add_to_tab_option
from grafana_tool.command_base import WriteCommand

VERB = {objects.ROW: "spostata", objects.PANEL: "spostato", objects.TAB: "spostato"}


class MoveCommand(WriteCommand):
    NAME = "move"
    HELP = "Sposta tab, righe o pannelli"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_kind_argument(parser)
        add_selectors(parser)
        parser.add_argument(
            "--to-row", dest="to_row", type=int, metavar="N",
            help="Riga di destinazione (obbligatorio per i pannelli)",
        )
        add_to_tab_option(parser)
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
    def _destination(args: argparse.Namespace) -> str:
        if args.before is not None:
            return f"prima dell'oggetto {args.before}"
        if args.after is not None:
            return f"dopo l'oggetto {args.after}"
        return "in cima" if args.position == "top" else "in fondo"

    @staticmethod
    def _check_destination(args: argparse.Namespace) -> None:
        """Rifiuta le destinazioni che non hanno senso per il tipo scelto."""
        if args.to_row is not None and (args.before is not None or args.after is not None):
            raise ValueError("Usare --to-row oppure --before/--after, non entrambi.")
        if args.kind == objects.TAB:
            if args.to_row is not None:
                raise ValueError("--to-row vale solo per i pannelli.")
            if args.to_tab is not None:
                raise ValueError("--to-tab vale solo per le righe: i tab non si annidano.")
            return
        if args.kind == objects.ROW:
            if args.to_row is not None:
                raise ValueError("--to-row vale solo per i pannelli.")
            return
        if args.to_tab is not None:
            raise ValueError(
                "--to-tab vale solo per le righe: un pannello segue la riga che lo contiene."
            )
        if args.to_row is None and args.before is None and args.after is None:
            raise ValueError(
                "Indicare la destinazione: --to-row N oppure --before/--after N."
            )

    def modify(self, db: dict, args: argparse.Namespace) -> dict:
        objects.require_selector(
            args.kind,
            ids=args.id,
            match_title=args.match_title,
            match_type=args.match_type,
            in_row=args.in_row,
        )
        self._check_destination(args)

        targets = objects.targets_from_args(db, args)
        if not targets:
            raise ValueError(
                f"Nessun {objects.NOUN[args.kind]} corrisponde ai selettori indicati."
            )

        for target in targets:
            self._move_one(db, target, args)

        noun = objects.PLURAL[args.kind].capitalize()
        print(f"{noun} spostate/i: {len(targets)}.")
        return db

    def _move_one(
        self, db: dict, target: objects.Target, args: argparse.Namespace
    ) -> None:
        if target.kind == objects.TAB:
            objects.move_tab(
                db, target, before=args.before, after=args.after,
                position=args.position,
            )
            print(f"{target.label()} {VERB[objects.TAB]} {self._destination(args)}.")
            return

        if target.kind == objects.ROW:
            if args.to_tab is not None:
                objects.set_tab(db, target, args.to_tab)
            if args.before is not None or args.after is not None or args.position == "top":
                objects.move_row(
                    db, target, before=args.before, after=args.after,
                    position=args.position,
                )
                print(f"{target.label()} {VERB[objects.ROW]} {self._destination(args)}.")
            return

        if args.to_row is not None:
            objects.move_panel(db, target, args.to_row, position=args.position)
            print(f"{target.label()} {VERB[objects.PANEL]} nella riga {args.to_row}.")
        else:
            objects.move_panel_relative(
                db, target, args.before if args.before is not None else args.after,
                after=args.after is not None,
            )
            print(f"{target.label()} {VERB[objects.PANEL]} {self._destination(args)}.")


command = MoveCommand()
