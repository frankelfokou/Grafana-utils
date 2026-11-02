"""extract-row: estrae una row da una dashboard e produce una dashboard minima.

Implementato come `WriteCommand` (Template Method): `modify` trasforma il
dashboard sorgente (caricato da `--from-dashboard`) nella dashboard minima
contenente solo la row matchata.
"""
from __future__ import annotations

import argparse
import copy

from grafana_tool.cli_common import add_title_options
from grafana_tool.command_base import WriteCommand
from grafana_tool.dashboard_factory import minimal_dashboard
from grafana_tool.identity import (
    dedupe_panel_titles,
    parse_inventory,
    seal_new_dashboard,
)
from grafana_tool.io import load_json
from grafana_tool.model import (
    find_row,
    find_row_container_by_title,
    get_max_id,
    iter_all_panels,
    row_children,
    shift_grid_y,
)

NAME = "extract-row"
HELP = "Estrae una row in una dashboard minima"

DEFAULT_ROW_MATCH = r"(VISTA\s+SISTEMISTICA|Sistemistica)"


def _grid_y(panel: dict) -> int:
    gp = panel.get("gridPos")
    if isinstance(gp, dict):
        return int(gp.get("y", 0) or 0)
    return 0


class ExtractRowCommand(WriteCommand):
    NAME = "extract-row"
    HELP = "Estrae una row in una dashboard minima"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("--from-dashboard", required=True, help="Dashboard sorgente da cui estrarre la row")
        parser.add_argument("--row-match", default=DEFAULT_ROW_MATCH, help="Regex per matchare il titolo della row")
        parser.add_argument("--row-id", type=int, default=None,
                            help="ID della row da estrarre (alternativo a --row-match)")
        parser.add_argument("--title",
                            help="Titolo della dashboard di output (default: titolo della row)")
        parser.add_argument("--uid",
                            help="uid della dashboard di output (default: generato, verificato contro l'inventario)")
        parser.add_argument("--existing-dashboards", metavar="FILE",
                            help="Inventario JSON delle dashboard già presenti in Grafana "
                                 "(lista di {uid,title} o risposta di GET /api/search)")
        parser.add_argument("--panel-id-base", type=int,
                            help="Primo id dei pannelli (default: max id della sorgente + 1)")
        add_title_options(parser)
        super().configure(parser)

    def run(self, args: argparse.Namespace) -> int:
        """Sovrascrive run perché non c'è un argomento posizionale `file`.

        Imposta args.file a from-dashboard così che save_and_validate risolva
        correttamente il path di output predefinito (<from-dashboard>_out.json).
        """
        args.file = args.from_dashboard
        return super().run(args)

    def _find_row(self, db: dict, args: argparse.Namespace) -> dict:
        if args.row_id is not None:
            row = find_row(db, args.row_id)
            if row is None:
                raise ValueError(f"Riga {args.row_id} non trovata in {args.from_dashboard}")
            return row
        _, _, row = find_row_container_by_title(db, args.row_match)
        if not row:
            raise ValueError(f"Nessuna row matchata con '{args.row_match}' in {args.from_dashboard}")
        return row

    def _inventory(self, args: argparse.Namespace) -> tuple[set[str], set[str]]:
        """uid e titoli delle dashboard già presenti in Grafana, se indicati."""
        if not args.existing_dashboards:
            return set(), set()
        return parse_inventory(load_json(args.existing_dashboards))

    def modify(self, db: dict, args: argparse.Namespace) -> dict:
        row = self._find_row(db, args)
        children = row_children(db, row)
        source_max_id = get_max_id(db)

        # Una riga espansa non ha figli in `row["panels"]`: Grafana tiene i
        # pannelli top-level subito dopo la riga. Nell'estrazione li ripetiamo
        # nella stessa forma (riga + pannelli fratelli) per restare fedeli
        # all'originale; una riga collassata conserva i figli annidati.
        is_expanded = row.get("collapsed") is False and not (row.get("panels") or [])

        row_copy = copy.deepcopy(row)
        if is_expanded:
            row_copy["panels"] = []
            extracted = [row_copy] + [copy.deepcopy(c) for c in children]
        else:
            extracted = [row_copy]

        # ID nuovi e consecutivi per la row e per tutti i pannelli estratti.
        # La base parte dopo l'ultimo id della sorgente: i numeri del file di
        # output non coincidono con quelli già presenti in Grafana.
        block = list(iter_all_panels({"panels": extracted}))
        base_id = args.panel_id_base if args.panel_id_base is not None else source_max_id + 1
        if base_id < 1:
            raise ValueError("--panel-id-base deve essere >= 1.")
        for offset, panel in enumerate(block):
            panel["id"] = base_id + offset

        # Con --dedupe-titles i titoli dei pannelli sono resi unici tra loro;
        # i titoli della sorgente non sono un conflitto, perché la dashboard
        # è nuova (uid nuovo).
        renamed = dedupe_panel_titles(block) if args.dedupe_titles else 0

        # gridPos: porta il blocco estratto a partire da y=0.
        min_y = min((_grid_y(p) for p in block if isinstance(p.get("gridPos"), dict)), default=0)
        if min_y:
            shift_grid_y(extracted, -min_y)
        gp = row_copy.get("gridPos")
        if not isinstance(gp, dict):
            row_copy["gridPos"] = {"h": 1, "w": 24, "x": 0, "y": 0}

        content = [p for p in block if p.get("type") != "row"]
        db_min = minimal_dashboard(
            title=row_copy.get("title") or "Extracted row",
            panels=extracted,
            source=db,
        )

        # La dashboard estratta è un oggetto nuovo: uid generato, id nullo,
        # version 1 e titolo assente dall'inventario indicato.
        inv_uids, inv_titles = self._inventory(args)
        source_uid = db.get("uid")
        source_title = db.get("title")
        taken_uids = set(inv_uids) | ({source_uid} if isinstance(source_uid, str) and source_uid else set())
        taken_titles = set(inv_titles) | ({source_title} if isinstance(source_title, str) and source_title else set())
        ident = seal_new_dashboard(
            db_min,
            uid=args.uid,
            title=args.title or row_copy.get("title"),
            taken_uids=taken_uids,
            taken_titles=taken_titles,
        )

        print(
            f"Row '{row_copy.get('title')}' estratta con {len(content)} pannelli "
            f"(id {block[0]['id'] if block else 0}..{block[-1]['id'] if block else 0})."
        )
        if renamed:
            print(f"Titoli pannelli disambiguati: {renamed}.")
        print(f"Dashboard di output: uid '{ident.uid}', titolo '{ident.title}'.")
        return db_min


command = ExtractRowCommand()
