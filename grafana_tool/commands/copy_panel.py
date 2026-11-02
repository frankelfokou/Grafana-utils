"""copy-panel: duplica un singolo pannello con un nuovo id."""
from __future__ import annotations

import argparse
import copy

from grafana_tool.cli_common import add_title_options, add_write_options
from grafana_tool.identity import all_titles, dedupe_panel_titles
from grafana_tool.io import load_dashboard
from grafana_tool.model import (
    append_to_row_block,
    find_panel_container,
    find_row,
    get_max_id,
    iter_panels,
)
from grafana_tool.persist import save_and_validate
from grafana_tool.replacements import apply_in_panel, parse_replacements

NAME = "copy-panel"
HELP = "Duplica un singolo pannello (con nuovo id)"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--panel-id", type=int, required=True, help="ID del pannello da copiare")
    parser.add_argument("--target-row", type=int, help="Riga di destinazione (default: stessa riga)")
    parser.add_argument("--new-title", help="Titolo del clone")
    parser.add_argument("--replace", action="append", default=[], metavar="OLD=NEW",
                        help="Sostituzione applicata a target[*].expr del clone (ripetibile)")
    add_title_options(parser)
    add_write_options(parser)

def run(args: argparse.Namespace) -> int:
    db = load_dashboard(args.file)

    container, idx = find_panel_container(db, args.panel_id)
    if container is None:
        raise ValueError(f"Pannello {args.panel_id} non trovato.")
    panel = container[idx]
    if panel.get("type") == "row":
        raise ValueError("copy-panel non copia righe; usare --panel-id di un pannello.")

    clone = copy.deepcopy(panel)
    # Riassegna l'ID anche ai pannelli annidati, altrimenti il clone duplica ID.
    next_id = get_max_id(db)
    for sub in iter_panels([clone]):
        next_id += 1
        sub["id"] = next_id
    if args.new_title:
        clone["title"] = args.new_title
    # Il clone vive nella stessa dashboard: con --dedupe-titles il titolo non
    # ripete quello già presente (né quello dell'originale).
    renamed = dedupe_panel_titles([clone], all_titles(db)) if args.dedupe_titles else 0
    apply_in_panel(clone, parse_replacements(args.replace))

    if args.target_row is not None:
        tgt = find_row(db, args.target_row)
        if tgt is None:
            raise ValueError(f"Riga {args.target_row} non trovata.")
        append_to_row_block(db, tgt, clone)
    else:
        container.insert(idx + 1, clone)

    print(f"Pannello {args.panel_id} copiato come id {clone['id']}.")
    if renamed:
        print(f"Titoli pannelli disambiguati: {renamed}.")
    return save_and_validate(db, args)
