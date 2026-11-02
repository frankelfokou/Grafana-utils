"""append-row: aggiunge una row parametrizzata a una dashboard Grafana.

Implementato come `WriteCommand` (Template Method): il metodo `modify`
contiene la logica specifica, mentre `run` (ereditato) gestisce load,
deep-copy, save e validazione finale.
"""
from __future__ import annotations

import argparse
import copy
from pathlib import Path

from grafana_tool.cli_common import add_title_options
from grafana_tool.command_base import WriteCommand
from grafana_tool.identity import (
    all_titles,
    dedupe_panel_titles,
    id_range_collisions,
    unique_title,
)
from grafana_tool.io import load_dashboard
from grafana_tool.model import (
    find_row_by_title,
    find_row_container_by_title,
    get_max_id,
    iter_panels,
    max_y,
    remove_row_block,
    renumber_ids,
    row_children,
)
from grafana_tool.params import ParamLoader
from grafana_tool.placeholders import apply_placeholders
from grafana_tool.namespace_normalizer import normalize_namespace
from grafana_tool.replacements import apply_in_panel, parse_replacements

NAME = "append-row"
HELP = "Aggiunge una row parametrizzata alla dashboard"

DEFAULT_TEMPLATE = "templates/system-view.row.tpl.json"
DEFAULT_ROW_MATCH = r"(VISTA\s+SISTEMISTICA|Sistemistica)"

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent


def _resolve_template(path: str) -> str:
    p = Path(path)
    if not p.exists():
        cand = _PROJECT_ROOT / path
        if cand.exists():
            return str(cand)
    return str(p)


def _build_params(args: argparse.Namespace, file_params: dict[str, str]) -> dict[str, str]:
    """Assembla i parametri: file (valori vuoti ignorati) → CLI override → default."""
    p: dict[str, str] = {}
    for k, v in (file_params or {}).items():
        p[str(k)] = str(v)

    if args.namespace is not None:
        p["NAMESPACE"] = args.namespace
    if args.cluster_gen is not None:
        p["CLUSTER_GEN"] = str(args.cluster_gen)
    if args.datasource is not None:
        p["DATASOURCE_UID"] = args.datasource
    if args.title_prefix is not None:
        p["TITLE_PREFIX"] = args.title_prefix
    if args.row_title is not None:
        p["ROW_TITLE"] = args.row_title

    p.setdefault("NAMESPACE", "universo-on-line-feu-up")
    p.setdefault("CLUSTER_GEN", "2")
    p.setdefault("DATASOURCE_UID", "QEIISg1Vz")
    p.setdefault("TITLE_PREFIX", "")
    p.setdefault("ROW_TITLE", f"VISTA SISTEMISTICA - {p['NAMESPACE']}")
    return p


def _load_template_row(args: argparse.Namespace) -> dict:
    if args.from_dashboard:
        db = load_dashboard(args.from_dashboard)
        src = find_row_by_title(db, args.row_match)
        if src is None:
            raise ValueError(f"Nessuna row matchata in {args.from_dashboard}")
        # `row_children` comprende anche i pannelli delle righe espanse, che
        # Grafana salva come pannelli top-level dopo la riga.
        children = row_children(db, src)
        row = copy.deepcopy(src)
        row["panels"] = copy.deepcopy(children)
        row["collapsed"] = True
        return row

    tpl = load_dashboard(_resolve_template(args.template))
    if tpl.get("type") == "row":
        return copy.deepcopy(tpl)
    if isinstance(tpl.get("panels"), list):
        rows = [p for p in tpl["panels"] if isinstance(p, dict) and p.get("type") == "row"]
        if not rows:
            raise ValueError("Il template non contiene alcuna row.")
        return copy.deepcopy(rows[0])
    raise ValueError("Template non valido.")


def _assigned_ids(row: dict) -> int:
    """Quanti id assegna `renumber_ids` alla riga (riga + figli + nipoti)."""
    n = 1
    for panel in row.get("panels") or []:
        n += 1
        n += len(panel.get("panels") or [])
    return n


class AppendRowCommand(WriteCommand):
    NAME = "append-row"
    HELP = "Aggiunge una row parametrizzata alla dashboard"

    def configure(self, parser: argparse.ArgumentParser) -> None:
        parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
        parser.add_argument(
            "--template", default=DEFAULT_TEMPLATE,
            help="Template row (default: templates/system-view.row.tpl.json)",
        )
        parser.add_argument("--from-dashboard", help="Estrai la row da questa dashboard esistente")
        parser.add_argument("--row-match", default=DEFAULT_ROW_MATCH, help="Regex per matchare il titolo della row")
        parser.add_argument("--params", help="File params JSON o YAML (opzionale)")
        parser.add_argument("--namespace", help="Valore per ${NAMESPACE}")
        parser.add_argument("--cluster-gen", help="Valore per ${CLUSTER_GEN}")
        parser.add_argument("--datasource", help="Valore per ${DATASOURCE_UID}")
        parser.add_argument("--title-prefix", help="Valore per ${TITLE_PREFIX}")
        parser.add_argument("--row-title", help="Valore per ${ROW_TITLE}")
        parser.add_argument(
            "--replace", action="append", default=[], metavar="OLD=NEW",
            help="Sostituzione applicata a target[*].expr dei pannelli (ripetibile)",
        )
        parser.add_argument("--base-id", type=int, help="ID base per la nuova row (default: max+1)")
        parser.add_argument("--position", choices=["top", "bottom"], default="bottom", help="Posizione della row")
        parser.add_argument(
            "--on-existing", choices=["replace", "skip", "append", "error"], default="replace",
            help="Comportamento se una row matchante esiste già",
        )
        parser.add_argument("--collapsed", dest="collapsed", action="store_true", default=True, help="Row collassata (default)")
        parser.add_argument("--expanded", dest="collapsed", action="store_false", help="Row espansa")
        parser.add_argument("--no-normalize", action="store_true", help="Non convertire namespace=\"...\" in namespace=~\"...\"")
        add_title_options(parser)
        super().configure(parser)

    def modify(self, db: dict, args: argparse.Namespace) -> dict:
        loader = ParamLoader()
        file_params = loader.load(args.params)
        params = _build_params(args, file_params)

        template_row = _load_template_row(args)
        new_row = apply_placeholders(copy.deepcopy(template_row), params)
        new_row["collapsed"] = bool(args.collapsed)

        if not args.no_normalize:
            new_row = normalize_namespace(new_row)

        if "panels" not in new_row:
            new_row["panels"] = []

        repl = parse_replacements(args.replace)
        for p in iter_panels([new_row]):
            apply_in_panel(p, repl)

        _, _, existing_row = find_row_container_by_title(db, args.row_match)
        if existing_row is not None:
            if args.on_existing == "error":
                raise ValueError(f"Row esistente con titolo '{existing_row.get('title')}'")
            if args.on_existing == "skip":
                titolo = existing_row.get("title")
                print(f"Row già presente ('{titolo}'), skip.")
                return db  # nessuna modifica, save_and_validate scrive l'originale
            if args.on_existing == "replace":
                titolo = existing_row.get("title")
                # Per una riga espansa vanno rimossi anche i pannelli
                # top-level che la seguono, altrimenti restano orfani.
                remove_row_block(db, existing_row.get("id"))
                print(f"Row esistente '{titolo}' rimossa.")

        base_id = args.base_id if args.base_id is not None else get_max_id(db) + 1
        clashes = id_range_collisions(db, base_id, _assigned_ids(new_row))
        if clashes:
            raise ValueError(
                f"--base-id {base_id} collide con id già presenti: {clashes}"
            )
        renumber_ids(new_row, base_id)

        # Titoli: con --dedupe-titles la nuova riga e i suoi pannelli non
        # riusano nomi già presenti. Il titolo si calcola dopo l'eventuale
        # rimozione della riga sostituita da --on-existing.
        taken_titles = all_titles(db)
        if args.dedupe_titles:
            new_row["title"] = unique_title(params["ROW_TITLE"], taken_titles)
            renamed = dedupe_panel_titles([new_row], taken_titles)
        else:
            new_row["title"] = params["ROW_TITLE"]
            renamed = 0

        # Una riga espansa non può tenere i figli in `row["panels"]`:
        # Grafana li vuole top-level subito dopo. Li separiamo qui.
        exploded: list[dict] = []
        if new_row.get("collapsed") is False and new_row.get("panels"):
            exploded = list(new_row["panels"])
            new_row["panels"] = []

        def _stack(y_start: int) -> int:
            """Dispone i pannelli esplosi sotto la riga; ritorna l'altezza usata."""
            y = y_start
            for child in exploded:
                gp = child.get("gridPos") if isinstance(child.get("gridPos"), dict) else {}
                gp["y"] = y
                child["gridPos"] = gp
                y += int(gp.get("h", 4) or 4)
            return max(1, y - y_start)

        if args.position == "top":
            row_h = 1 + (sum(int((c.get("gridPos") or {}).get("h", 4) or 4) for c in exploded) if exploded else 0)
            for p in db.get("panels", []) or []:
                gp = p.get("gridPos")
                if gp is not None:
                    gp["y"] = int(gp.get("y", 0) or 0) + row_h
            for r in db.get("rows", []) or []:
                gp = r.get("gridPos")
                if gp is not None:
                    gp["y"] = int(gp.get("y", 0) or 0) + row_h
            new_row["gridPos"] = {"h": 1, "w": 24, "x": 0, "y": 0}
            _stack(1)
            db.setdefault("panels", [])[0:0] = [new_row] + exploded
        else:
            y = max_y(db)
            new_row["gridPos"] = {"h": 1, "w": 24, "x": 0, "y": y}
            if exploded:
                _stack(y + 1)
            db.setdefault("panels", []).append(new_row)
            db["panels"].extend(exploded)

        n = len(new_row.get("panels", []) or []) + len(exploded)
        print(
            f"Row '{new_row['title']}' aggiunta (id {base_id}..{base_id + n - 1}, {n} pannelli)."
        )
        if renamed:
            print(f"Titoli pannelli disambiguati: {renamed}.")
        return db


command = AppendRowCommand()

# Esposizione a livello di modulo per compatibilità con ALL_COMMANDS
# (è un'istanza, espone NAME, HELP, configure, run).
