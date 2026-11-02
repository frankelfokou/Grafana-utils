"""create: crea una riga o un pannello.

Due sorgenti possibili, uguali per entrambi i tipi:

  - `--from-id N` copia un oggetto esistente (con i suoi figli);
  - `--template FILE` istanzia un template, applicando `${...}` e `--replace`.

Per le righe il template ha un default, quindi `create row` senza sorgente
riproduce la riga di sistema; per i pannelli la sorgente è obbligatoria.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path
from typing import Any

from grafana_tool import objects
from grafana_tool.cli_common import (
    add_collapsed_options,
    add_dedupe_option,
    add_kind_argument,
    add_replace_option,
    add_title_option,
)
from grafana_tool.command_base import WriteCommand
from grafana_tool.identity import (
    all_titles,
    dedupe_panel_titles,
    id_range_collisions,
    normalize_title,
    unique_title,
)
from grafana_tool.io import load_dashboard
from grafana_tool.model import (
    find_panel_container,
    get_max_id,
    iter_panels,
    iter_rows,
    max_y,
    remove_row_block,
    renumber_ids,
    require_row,
    row_children,
    shift_dashboard_grid_y,
    stack_grid_y,
)
from grafana_tool.namespace_normalizer import normalize_namespace
from grafana_tool.params import ParamLoader
from grafana_tool.placeholders import apply_placeholders
from grafana_tool.replacements import apply_in_panel, parse_replacements

DEFAULT_ROW_TEMPLATE = "templates/system-view.row.tpl.json"
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
ON_EXISTING = ("error", "replace", "skip", "append")
PARAM_DEFAULTS = {
    "NAMESPACE": "universo-on-line-feu-up",
    "CLUSTER_GEN": "2",
    "DATASOURCE_UID": "QEIISg1Vz",
    "TITLE_PREFIX": "",
}


def _load_template(path: str) -> dict[str, Any]:
    """Carica il template, cercandolo anche dalla radice del progetto."""
    candidate = Path(path)
    if not candidate.exists():
        rooted = PROJECT_ROOT / path
        if rooted.exists():
            candidate = rooted
    return load_dashboard(str(candidate))


def _pick_template_object(data: dict[str, Any], kind: str) -> dict[str, Any]:
    """Estrae dal template il primo oggetto del tipo richiesto."""
    if kind == objects.ROW:
        if data.get("type") == "row":
            return data
        for item in data.get("panels") or []:
            if isinstance(item, dict) and item.get("type") == "row":
                return item
        raise ValueError("Il template non contiene alcuna riga.")

    roots = data.get("panels") if isinstance(data.get("panels"), list) else [data]
    for item in iter_panels([r for r in roots if isinstance(r, dict)]):
        if item.get("type") not in (None, "row"):
            return item
    raise ValueError("Il template non contiene alcun pannello.")


def _build_params(args: argparse.Namespace) -> dict[str, str]:
    """Assembla i parametri: file → CLI override → default."""
    params = {str(k): str(v) for k, v in ParamLoader().load(args.params).items()}

    # Una sola mappa opzione→segnaposto: aggiungere un parametro significa
    # toccare questa riga e non cinque blocchi condizionali.
    cli_params = {
        "NAMESPACE": args.namespace,
        "CLUSTER_GEN": args.cluster_gen,
        "DATASOURCE_UID": args.datasource_uid,
        "TITLE_PREFIX": args.title_prefix,
        "ROW_TITLE": args.title,
    }
    for name, value in cli_params.items():
        if value is not None:
            params[name] = str(value)

    for name, value in PARAM_DEFAULTS.items():
        params.setdefault(name, value)
    # Il titolo predefinito dipende dal namespace, quindi si calcola dopo.
    params.setdefault("ROW_TITLE", f"VISTA SISTEMISTICA - {params['NAMESPACE']}")
    return params


class CreateCommand(WriteCommand):
    NAME = "create"
    HELP = "Crea una riga o un pannello da un oggetto esistente o da un template"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_kind_argument(parser)
        parser.add_argument(
            "--from-id", dest="from_id", type=int, metavar="N",
            help="Copia l'oggetto con questo id",
        )
        parser.add_argument(
            "--template", metavar="FILE",
            help=f"Crea da un template JSON (default per row: {DEFAULT_ROW_TEMPLATE})",
        )
        add_title_option(parser, "Titolo del nuovo oggetto (default: quello della sorgente)")
        add_dedupe_option(parser)
        add_collapsed_options(parser, default=True)
        parser.add_argument(
            "--to-row", dest="to_row", type=int, metavar="N",
            help="Riga di destinazione del nuovo pannello",
        )
        parser.add_argument(
            "--position", choices=["top", "bottom"], default="bottom",
            help="In cima o in fondo alla dashboard/riga (default: bottom)",
        )
        add_replace_option(parser, "Sostituzione su target[*].expr dei nuovi pannelli (ripetibile)")
        parser.add_argument("--params", metavar="FILE",
                            help="Parametri per i segnaposto ${...} del template")
        parser.add_argument("--namespace", help="Valore per ${NAMESPACE}")
        parser.add_argument("--cluster-gen", dest="cluster_gen", help="Valore per ${CLUSTER_GEN}")
        parser.add_argument("--datasource-uid", dest="datasource_uid",
                            help="Valore per ${DATASOURCE_UID}")
        parser.add_argument("--title-prefix", dest="title_prefix", help="Valore per ${TITLE_PREFIX}")
        parser.add_argument(
            "--namespace-exact", dest="namespace_exact", action="store_true",
            help='Non riscrivere namespace="x" in namespace=~"x"',
        )
        parser.add_argument("--base-id", dest="base_id", type=int,
                            help="Primo id dei nuovi oggetti (default: max+1)")
        parser.add_argument(
            "--on-existing", dest="on_existing", choices=list(ON_EXISTING), default=None,
            help=(
                "Con --template: comportamento se esiste già una riga con lo stesso "
                "titolo (default: error)"
            ),
        )

    # --------------------------------------------------------- sorgente

    @staticmethod
    def _source(args: argparse.Namespace) -> tuple[str, str | None]:
        if args.from_id is not None and args.template is not None:
            raise ValueError("Usare --from-id oppure --template, non entrambi.")
        if args.from_id is not None:
            return "from-id", None
        if args.template is not None:
            return "template", args.template
        if args.kind == objects.ROW:
            return "template", DEFAULT_ROW_TEMPLATE
        raise ValueError("Specificare la sorgente: --from-id N oppure --template FILE.")

    # ----------------------------------------------------------- valori

    def _title(self, db: dict, args: argparse.Namespace, default: str) -> str:
        title = (args.title if args.title is not None else default).strip()
        if not title:
            raise ValueError("--title non può essere vuoto.")
        if args.dedupe_titles:
            title = unique_title(title, all_titles(db))
        return title

    def _assign_ids(self, db: dict, obj: dict, args: argparse.Namespace) -> int:
        """Numera l'oggetto e i suoi figli partendo da una base libera."""
        count = sum(1 for _ in iter_panels([obj]))
        base_id = args.base_id if args.base_id is not None else get_max_id(db) + 1
        if base_id < 1:
            raise ValueError("--base-id deve essere >= 1.")
        clashes = id_range_collisions(db, base_id, count)
        if clashes:
            raise ValueError(f"--base-id {base_id} collide con id già presenti: {clashes}")
        renumber_ids(obj, base_id)
        return base_id

    @staticmethod
    def _existing_row(db: dict, title: str) -> dict | None:
        wanted = normalize_title(title)
        for row in iter_rows(db):
            if normalize_title(row.get("title")) == wanted:
                return row
        return None

    # ------------------------------------------------------------ righe

    def _build_row(
        self, db: dict, args: argparse.Namespace, source: tuple[str, str | None]
    ) -> tuple[dict, int] | None:
        mode, template = source
        if mode == "from-id" and args.on_existing is not None:
            raise ValueError("--on-existing vale solo per i template di riga.")
        if mode == "from-id":
            src = require_row(db, args.from_id)
            row = copy.deepcopy(src)
            row["panels"] = [
                copy.deepcopy(c) for c in row_children(db, src) if isinstance(c, dict)
            ]
            default_title = src.get("title") or "Riga"
        else:
            row = copy.deepcopy(
                _pick_template_object(_load_template(template or ""), objects.ROW)
            )
            row = apply_placeholders(row, _build_params(args))
            if not args.namespace_exact:
                row = normalize_namespace(row)
            default_title = row.get("title") or "Riga"

        if args.to_row is not None:
            raise ValueError("--to-row vale solo per i pannelli.")
        if not isinstance(row.get("panels"), list):
            row["panels"] = []

        title = self._title(db, args, default_title)
        row["title"] = title

        if mode == "template":
            existing = self._existing_row(db, title)
            behavior = args.on_existing or "error"
            if existing is not None:
                if behavior == "error":
                    raise ValueError(
                        f"Esiste già la riga '{title}' (id {existing.get('id')}): "
                        "usare --on-existing replace|skip|append."
                    )
                if behavior == "skip":
                    print(f"Riga '{title}' già presente, nessuna modifica.")
                    return None
                if behavior == "replace":
                    remove_row_block(db, existing.get("id"))
                    print(f"Riga esistente '{title}' rimossa.")

        replacements = parse_replacements(args.replace)
        for panel in iter_panels([row]):
            apply_in_panel(panel, replacements)

        base_id = self._assign_ids(db, row, args)
        row["collapsed"] = bool(args.collapsed)

        renamed = dedupe_panel_titles([row], all_titles(db)) if args.dedupe_titles else 0
        return row, renamed

    def _place_row(self, db: dict, row: dict, args: argparse.Namespace) -> None:
        # Una riga espansa non può tenere i figli in `row["panels"]`:
        # Grafana li vuole top-level subito dopo. Li separiamo qui.
        exploded: list[dict] = []
        if row.get("collapsed") is False and row.get("panels"):
            exploded = list(row["panels"])
            row["panels"] = []

        if args.position == "top":
            row_h = 1 + (stack_grid_y(exploded, 1) if exploded else 0)
            shift_dashboard_grid_y(db, row_h)
            row["gridPos"] = {"h": 1, "w": 24, "x": 0, "y": 0}
            db.setdefault("panels", [])[0:0] = [row] + exploded
        else:
            y = max_y(db)
            row["gridPos"] = {"h": 1, "w": 24, "x": 0, "y": y}
            if exploded:
                stack_grid_y(exploded, y + 1)
            db.setdefault("panels", []).append(row)
            db["panels"].extend(exploded)

        n = len(row.get("panels") or []) + len(exploded)
        last = row["id"] + n - 1
        print(f"Riga '{row['title']}' creata con {n} pannelli (id {row['id']}..{last}).")

    # --------------------------------------------------------- pannelli

    def _build_panel(
        self, db: dict, args: argparse.Namespace, source: tuple[str, str | None]
    ) -> tuple[dict, objects.Target | None]:
        mode, template = source
        if mode == "from-id":
            anchor = objects.find_target(db, objects.PANEL, args.from_id)
            panel = copy.deepcopy(anchor.obj)
            default_title = anchor.title or "Pannello"
        else:
            anchor = None
            panel = copy.deepcopy(
                _pick_template_object(_load_template(template or ""), objects.PANEL)
            )
            panel = apply_placeholders(panel, _build_params(args))
            if not args.namespace_exact:
                panel = normalize_namespace(panel)
            default_title = panel.get("title") or "Pannello"

        if args.on_existing is not None:
            raise ValueError("--on-existing vale solo per i template di riga.")

        panel["title"] = self._title(db, args, default_title)
        apply_in_panel(panel, parse_replacements(args.replace))
        self._assign_ids(db, panel, args)
        return panel, anchor

    def _place_panel(
        self, db: dict, panel: dict, anchor: objects.Target | None, args: argparse.Namespace
    ) -> None:
        if args.to_row is not None:
            objects.insert_in_row(
                db, require_row(db, args.to_row), panel, position=args.position
            )
            where = f"nella riga {args.to_row}"
        elif anchor is not None:
            container, idx = find_panel_container(db, anchor.id)
            if container is None:
                raise ValueError(f"Pannello {anchor.id} non trovato.")
            container.insert(idx if args.position == "top" else idx + 1, panel)
            where = "accanto all'originale"
        else:
            db.setdefault("panels", []).append(panel)
            where = "in fondo alla dashboard"
        print(f"Pannello '{panel['title']}' creato con id {panel['id']} {where}.")

    # ----------------------------------------------------------- modify

    def modify(self, db: dict, args: argparse.Namespace) -> dict:
        source = self._source(args)
        if args.kind == objects.ROW:
            built = self._build_row(db, args, source)
            if built is None:  # --on-existing skip
                return db
            row, renamed = built
            self._place_row(db, row, args)
            self.report_renamed(renamed)
        else:
            panel, anchor = self._build_panel(db, args, source)
            self._place_panel(db, panel, anchor, args)
        return db


command = CreateCommand()
