"""extract: estrae una riga o un pannello in una dashboard minima.

Un solo comando per entrambi i tipi: cambia solo come si costruisce il
blocco estratto (la riga porta i suoi pannelli, il pannello è sé stesso).
Uid, id, titolo e `gridPos` vengono normalizzati allo stesso modo.
"""
from __future__ import annotations

import argparse
import copy

from grafana_tool import objects
from grafana_tool.cli_common import (
    add_dedupe_option,
    add_kind_argument,
    add_selectors,
    add_title_option,
)
from grafana_tool.command_base import WriteCommand
from grafana_tool.dashboard_factory import minimal_dashboard
from grafana_tool.identity import (
    dedupe_panel_titles,
    extend_text,
    parse_inventory,
    seal_new_dashboard,
)
from grafana_tool.io import load_json
from grafana_tool.model import (
    get_max_id,
    iter_all_panels,
    min_grid_y,
    row_children,
    shift_grid_y,
)

ROOT_GRID = {
    objects.ROW: {"h": 1, "w": 24, "x": 0, "y": 0},
    objects.PANEL: {"h": 8, "w": 12, "x": 0, "y": 0},
}
PAST = {objects.ROW: "estratta", objects.PANEL: "estratto"}


class ExtractCommand(WriteCommand):
    NAME = "extract"
    HELP = "Estrae una riga o un pannello in una dashboard minima"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_kind_argument(parser)
        add_selectors(parser)
        add_title_option(parser, "Titolo della dashboard di output (default: titolo dell'oggetto)")
        parser.add_argument(
            "--uid",
            help="uid della dashboard di output (default: generato, verificato contro l'inventario)",
        )
        parser.add_argument(
            "--existing-dashboards", dest="existing_dashboards", metavar="FILE",
            help=(
                "Inventario JSON delle dashboard già presenti in Grafana "
                "(lista di {uid,title} o risposta di GET /api/search)"
            ),
        )
        parser.add_argument(
            "--base-id", dest="base_id", type=int,
            help="Primo id dei pannelli (default: max id della sorgente + 1)",
        )
        add_dedupe_option(parser)

    def _inventory(self, args: argparse.Namespace) -> tuple[set[str], set[str]]:
        """uid e titoli delle dashboard già presenti in Grafana, se indicati."""
        if not args.existing_dashboards:
            return set(), set()
        return parse_inventory(load_json(args.existing_dashboards))

    @staticmethod
    def _block(db: dict, target: objects.Target) -> list[dict]:
        """Radici del blocco da estrarre, nella forma in cui Grafana le salva."""
        if target.kind == objects.PANEL:
            return [copy.deepcopy(target.obj)]

        # Una riga espansa non ha figli in `row["panels"]`: Grafana tiene i
        # pannelli top-level subito dopo la riga. Nell'estrazione ripetiamo la
        # stessa forma; una riga collassata conserva i figli annidati.
        row_copy = copy.deepcopy(target.obj)
        expanded = target.obj.get("collapsed") is False and not (target.obj.get("panels") or [])
        if expanded:
            row_copy["panels"] = []
            children = [c for c in row_children(db, target.obj) if isinstance(c, dict)]
            return [row_copy] + [copy.deepcopy(c) for c in children]
        return [row_copy]

    def modify(self, db: dict, args: argparse.Namespace) -> dict:
        objects.require_selector(
            args.kind,
            ids=args.id,
            match_title=args.match_title,
            match_type=args.match_type,
            in_row=args.in_row,
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
        if len(targets) > 1:
            raise ValueError(
                f"Estrazione di un solo oggetto alla volta: {len(targets)} selezionati."
            )
        target = targets[0]

        extracted = self._block(db, target)
        block = list(iter_all_panels({"panels": extracted}))

        # Id nuovi e consecutivi: la base parte dopo l'ultimo id della sorgente,
        # così l'output non riusa i numeri già presenti in Grafana.
        base_id = args.base_id if args.base_id is not None else get_max_id(db) + 1
        if base_id < 1:
            raise ValueError("--base-id deve essere >= 1.")
        for offset, panel in enumerate(block):
            panel["id"] = base_id + offset

        renamed = dedupe_panel_titles(block) if args.dedupe_titles else 0

        # gridPos: porta il blocco estratto a partire da y=0.
        min_y = min_grid_y(block)
        if min_y:
            shift_grid_y(extracted, -min_y)
        for root in extracted:
            if not isinstance(root.get("gridPos"), dict):
                root["gridPos"] = dict(ROOT_GRID[args.kind])

        content = [p for p in block if p.get("type") != "row"]
        base_title = target.obj.get("title") or f"Extracted {args.kind}"
        db_min = minimal_dashboard(title=base_title, panels=extracted, source=db)

        # La dashboard di output è un oggetto nuovo: uid generato, id nullo,
        # version 1 e titolo assente dall'inventario indicato. Né l'uid né il
        # titolo della sorgente possono essere riusati: la sorgente resta.
        inv_uids, inv_titles = self._inventory(args)
        taken_uids = set(inv_uids)
        extend_text(taken_uids, db.get("uid"))
        taken_titles = set(inv_titles)
        extend_text(taken_titles, db.get("title"))
        ident = seal_new_dashboard(
            db_min,
            uid=args.uid,
            title=args.title or base_title,
            taken_uids=taken_uids,
            taken_titles=taken_titles,
        )

        print(
            f"{target.label()} {PAST[args.kind]} con {len(content)} pannelli "
            f"(id {block[0]['id'] if block else 0}..{block[-1]['id'] if block else 0})."
        )
        self.report_renamed(renamed)
        print(f"Dashboard di output: uid '{ident.uid}', titolo '{ident.title}'.")
        return db_min


command = ExtractCommand()
