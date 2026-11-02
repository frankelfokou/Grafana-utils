"""list: elenca righe o pannelli.

Primo comando del blocco CRUD unificato: il tipo è un argomento
posizionale (`row` o `panel`) e i selettori sono gli stessi per entrambi.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from grafana_tool import objects
from grafana_tool.cli_common import add_format_option, add_kind_argument, add_selectors
from grafana_tool.command_base import ReadCommand
from grafana_tool.model import row_children


class ListCommand(ReadCommand):
    NAME = "list"
    HELP = "Elenca righe o pannelli"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_kind_argument(parser)
        add_selectors(parser)
        add_format_option(parser)

    # ------------------------------------------------------------- righe

    @staticmethod
    def _row_record(db: dict[str, Any], target: objects.Target) -> dict[str, Any]:
        return {
            "kind": objects.ROW,
            "id": target.id,
            "title": target.obj.get("title") or "",
            "collapsed": target.obj.get("collapsed"),
            "panel_count": len(row_children(db, target.obj)),
        }

    @staticmethod
    def _panel_record(target: objects.Target) -> dict[str, Any]:
        return {
            "kind": objects.PANEL,
            "id": target.id,
            "title": target.obj.get("title") or "",
            "type": target.panel_type,
            "row_id": target.parent.get("id") if target.parent else None,
        }

    # ----------------------------------------------------------- stampa

    @staticmethod
    def _print_rows(db: dict, targets: list[objects.Target]) -> None:
        if not targets:
            print("Nessuna riga trovata.")
            return
        print(f"{'ID':>6}  {'Titolo':<50}  {'Pannelli':>8}  {'Collapsed':>9}")
        print("-" * 82)
        for t in targets:
            title = t.obj.get("title") or "(senza titolo)"
            n = len(row_children(db, t.obj))
            collapsed = str(t.obj.get("collapsed", ""))
            print(f"{str(t.id):>6}  {title:<50}  {n:>8}  {collapsed:>9}")

    @staticmethod
    def _print_panels(targets: list[objects.Target]) -> None:
        if not targets:
            print("Nessun pannello trovato.")
            return
        for t in targets:
            owner = f"riga {t.parent.get('id', '?')}" if t.parent else "nessuna riga"
            title = t.obj.get("title") or "(senza titolo)"
            print(f"- [{t.id}] {t.panel_type or '?'}: {title}  ({owner})")
            for target in t.obj.get("targets") or []:
                if isinstance(target, dict) and target.get("expr"):
                    expr = str(target["expr"])
                    if len(expr) > 100:
                        expr = expr[:97] + "..."
                    print(f"    expr: {expr}")

    # ----------------------------------------------------------- perform

    def perform(self, db: dict, args: argparse.Namespace) -> int:
        targets = objects.select_targets(
            db, args.kind,
            ids=args.id,
            match_title=args.match_title,
            match_type=args.match_type,
            in_row=args.in_row,
        )

        if args.format == "json":
            if args.kind == objects.ROW:
                payload = [self._row_record(db, t) for t in targets]
            else:
                payload = [self._panel_record(t) for t in targets]
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        if args.kind == objects.ROW:
            self._print_rows(db, targets)
        else:
            self._print_panels(targets)
        return 0


command = ListCommand()
