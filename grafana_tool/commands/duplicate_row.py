"""duplicate-row: crea una nuova riga copiando i pannelli di un'altra.

La riga di partenza non viene modificata e non viene eliminato nulla:
la copia viene inserita dopo il blocco della sorgente (per una riga
espansa, dopo il suo ultimo pannello) con id nuovi per la riga e per
tutti i suoi pannelli (anche quelli annidati).
"""
from __future__ import annotations

import argparse
import copy

from grafana_tool.cli_common import add_title_options, add_write_options
from grafana_tool.identity import all_titles, dedupe_panel_titles, unique_title
from grafana_tool.io import load_dashboard
from grafana_tool.model import (
    find_row,
    get_max_id,
    insert_row_after_block,
    iter_panels,
    row_children,
)
from grafana_tool.persist import save_and_validate
from grafana_tool.replacements import apply_in_panel, parse_replacements

NAME = "duplicate-row"
HELP = "Crea una nuova riga copiando i pannelli di un'altra"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--source", type=int, required=True,
                        help="ID della riga da copiare")
    parser.add_argument("--new-title",
                        help="Titolo della nuova riga (default: <titolo>_COPY)")
    parser.add_argument("--replace", action="append", default=[], metavar="OLD=NEW",
                        help="Sostituzione applicata a target[*].expr dei cloni (ripetibile)")
    add_title_options(parser)
    add_write_options(parser)

def run(args: argparse.Namespace) -> int:
    db = load_dashboard(args.file)
    repl = parse_replacements(args.replace)

    src = find_row(db, args.source)
    if src is None:
        raise ValueError(f"Riga sorgente {args.source} non trovata.")

    # `row_children` risolve anche le righe espanse, i cui pannelli sono
    # top-level subito dopo la riga e non dentro `row["panels"]`.
    children = row_children(db, src)
    max_id = get_max_id(db)
    # Titoli già presenti: la copia nasce nella stessa dashboard, quindi non
    # può riusare un nome esistente senza renderlo ambiguo.
    taken_titles = all_titles(db)

    new_row = copy.deepcopy(src)
    max_id += 1
    new_row["id"] = max_id
    base = (src.get("title") or "riga").strip()
    row_title = args.new_title or f"{base}_COPY"
    if args.dedupe_titles:
        row_title = unique_title(row_title, taken_titles)
    new_row["title"] = row_title
    # La copia porta i pannelli dentro di sé: deve essere collassata, altrimenti
    # Grafana ignorerebbe `row["panels"]`.
    new_row["collapsed"] = True

    clones = []
    for p in children:
        clone = copy.deepcopy(p)
        for sub in iter_panels([clone]):
            max_id += 1
            sub["id"] = max_id
        apply_in_panel(clone, repl)
        clones.append(clone)
    new_row["panels"] = clones

    renamed = dedupe_panel_titles(clones, taken_titles) if args.dedupe_titles else 0

    insert_row_after_block(db, args.source, new_row)
    print(
        f"Nuova riga {new_row['id']} \"{new_row['title']}\" creata dopo la riga "
        f"{args.source}, con {len(clones)} pannelli."
    )
    if renamed:
        print(f"Titoli pannelli disambiguati: {renamed}.")
    return save_and_validate(db, args)
