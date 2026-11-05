"""list: elenca righe, pannelli o tab.

Primo comando del blocco CRUD unificato: il tipo è un argomento
posizionale (`row`, `panel` o `tab`) e i selettori sono gli stessi per
tutti.
"""
from __future__ import annotations

import argparse
import json
from typing import Any

from grafana_tool import objects, tabs
from grafana_tool.cli_common import add_format_option, add_kind_argument, add_selectors
from grafana_tool.command_base import ReadCommand
from grafana_tool.model import row_children


class ListCommand(ReadCommand):
    NAME = "list"
    HELP = "Elenca righe, pannelli o tab"

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
    def _panel_record(db: dict[str, Any], target: objects.Target) -> dict[str, Any]:
        return {
            "kind": objects.PANEL,
            "id": target.id,
            "title": target.obj.get("title") or "",
            "type": target.panel_type,
            "row_id": target.parent.get("id") if target.parent else None,
            "tab_id": objects.tab_of_target(db, target),
        }

    @staticmethod
    def _tab_record(db: dict[str, Any], target: objects.Target) -> dict[str, Any]:
        return {
            "kind": objects.TAB,
            "id": target.id,
            "title": target.obj.get("title") or "",
            "row_count": len(tabs.rows_of(db, target.id)),
            "panel_count": len(tabs.panels_of(db, target.id)),
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
    def _print_tabs(db: dict, targets: list[objects.Target]) -> None:
        if not targets:
            print("Nessun tab trovato.")
            return
        print(f"{'ID':>6}  {'Titolo':<50}  {'Righe':>6}  {'Pannelli':>8}")
        print("-" * 76)
        for t in targets:
            title = t.obj.get("title") or "(senza titolo)"
            print(
                f"{str(t.id):>6}  {title:<50}  "
                f"{len(tabs.rows_of(db, t.id)):>6}  "
                f"{len(tabs.panels_of(db, t.id)):>8}"
            )

    @staticmethod
    def _print_panels(db: dict, targets: list[objects.Target]) -> None:
        if not targets:
            print("Nessun pannello trovato.")
            return
        for t in targets:
            owner = f"riga {t.parent.get('id', '?')}" if t.parent else "nessuna riga"
            title = t.obj.get("title") or "(senza titolo)"
            tab_id = objects.tab_of_target(db, t)
            print(f"- [{t.id}] {t.panel_type or '?'}: {title}  ({owner}, tab {tab_id})")
            for target in t.obj.get("targets") or []:
                if isinstance(target, dict) and target.get("expr"):
                    expr = str(target["expr"])
                    if len(expr) > 100:
                        expr = expr[:97] + "..."
                    print(f"    expr: {expr}")

    # ----------------------------------------------------------- perform

    def perform(self, db: dict, args: argparse.Namespace) -> int:
        targets = objects.targets_from_args(db, args)

        if args.format == "json":
            if args.kind == objects.ROW:
                payload = [self._row_record(db, t) for t in targets]
            elif args.kind == objects.TAB:
                payload = [self._tab_record(db, t) for t in targets]
            else:
                payload = [self._panel_record(db, t) for t in targets]
            print(json.dumps(payload, indent=2, ensure_ascii=False))
            return 0

        if args.kind == objects.ROW:
            self._print_rows(db, targets)
        elif args.kind == objects.TAB:
            self._print_tabs(db, targets)
        else:
            self._print_panels(db, targets)
        return 0


command = ListCommand()
