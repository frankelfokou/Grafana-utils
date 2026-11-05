"""update: aggiorna righe o pannelli con le stesse impostazioni.

Il comando non distingue i tipi nell'interfaccia: `--title`,
`--collapsed`/`--expanded`, `--replace` e `--datasource` esistono per
entrambi. Le operazioni di contenuto (`--replace`, `--datasource`) su una
riga si applicano a tutti i pannelli che le appartengono.
"""
from __future__ import annotations

import argparse
from typing import Any

from grafana_tool import objects
from grafana_tool.cli_common import (
    add_collapsed_options,
    add_datasource_options,
    add_dedupe_option,
    add_kind_argument,
    add_replace_option,
    add_selectors,
    add_title_option,
)
from grafana_tool.command_base import WriteCommand
from grafana_tool.datasource import apply_datasource_to_panel
from grafana_tool.replacements import apply_in_panel, parse_replacements


class UpdateCommand(WriteCommand):
    NAME = "update"
    HELP = "Aggiorna titolo, stato, query o datasource di tab, righe o pannelli"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_kind_argument(parser)
        add_selectors(parser)
        add_title_option(parser)
        add_dedupe_option(parser)
        add_collapsed_options(parser, default=None)
        add_replace_option(parser, "Sostituzione su target[*].expr (ripetibile)")
        add_datasource_options(parser)

    @staticmethod
    def _has_changes(args: argparse.Namespace) -> bool:
        return (
            args.title is not None
            or args.collapsed is not None
            or bool(args.replace)
            or args.datasource is not None
        )

    def modify(self, db: dict, args: argparse.Namespace) -> dict:
        if args.datasource_type is not None and args.datasource is None:
            raise ValueError("--datasource-type richiede --datasource.")
        if args.datasource_create and args.datasource is None:
            raise ValueError("--datasource-create richiede --datasource.")
        if not self._has_changes(args):
            raise ValueError(
                "Nessuna modifica richiesta: usare --title, --collapsed, "
                "--expanded, --replace o --datasource."
            )

        targets = objects.targets_from_args(db, args)
        if not targets:
            raise ValueError(
                f"Nessun {objects.NOUN[args.kind]} corrisponde ai selettori indicati."
            )

        replacements = parse_replacements(args.replace)

        for target in targets:
            parts: list[str] = []

            if args.title is not None:
                title = objects.set_title(
                    db, target, args.title, dedupe=args.dedupe_titles
                )
                parts.append(f"titolo '{title}'")

            if args.collapsed is not None:
                objects.set_collapsed(db, target, bool(args.collapsed))
                parts.append(f"collapsed={bool(args.collapsed)}")

            content_hits = 0
            if replacements or args.datasource is not None:
                for panel in objects.content_panels(db, target):
                    hits = apply_in_panel(panel, replacements)
                    if args.datasource is not None:
                        hits += apply_datasource_to_panel(
                            panel, args.datasource, args.datasource_type,
                            force=args.datasource_create,
                        )
                    content_hits += hits
                if content_hits:
                    parts.append(f"{content_hits} modifiche al contenuto")

            print(f"{target.label()}: {', '.join(parts) if parts else 'nessun cambiamento'}")

        noun = objects.PLURAL[args.kind].capitalize()
        print(f"{noun} aggiornate/i: {len(targets)}.")
        return db


command = UpdateCommand()
