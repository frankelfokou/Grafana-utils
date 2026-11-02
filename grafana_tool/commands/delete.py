"""delete: elimina righe o pannelli.

Un solo comando per entrambi i tipi; il selettore è obbligatorio, così non
si cancella l'intera dashboard per errore.
"""
from __future__ import annotations

import argparse

from grafana_tool import objects
from grafana_tool.cli_common import add_kind_argument, add_selectors
from grafana_tool.command_base import WriteCommand


class DeleteCommand(WriteCommand):
    NAME = "delete"
    HELP = "Elimina righe o pannelli"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_kind_argument(parser)
        add_selectors(parser)
        parser.add_argument(
            "--keep-children", dest="keep_children", action="store_true",
            help="Per una riga: promuovi i pannelli a top-level invece di eliminarli",
        )

    def modify(self, db: dict, args: argparse.Namespace) -> dict:
        objects.require_selector(
            args.kind,
            ids=args.id,
            match_title=args.match_title,
            match_type=args.match_type,
            in_row=args.in_row,
        )
        if args.keep_children and args.kind != objects.ROW:
            raise ValueError("--keep-children vale solo per le righe.")

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

        removed_panels = 0
        for target in targets:
            removed = objects.remove(db, target, keep_children=args.keep_children)
            removed_panels += removed
            if target.kind == objects.ROW:
                if args.keep_children:
                    print(f"{target.label()} rimossa, pannelli mantenuti.")
                else:
                    print(f"{target.label()} rimossa con {removed} pannelli.")
            else:
                print(f"{target.label()} eliminato.")

        noun = objects.PLURAL[args.kind].capitalize()
        suffix = f" ({removed_panels} pannelli eliminati)" if args.kind == objects.ROW else ""
        print(f"{noun} eliminate/i: {len(targets)}{suffix}.")
        return db


command = DeleteCommand()
