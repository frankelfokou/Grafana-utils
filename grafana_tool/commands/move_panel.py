"""move-panel: sposta un pannello esistente in un'altra riga."""
from __future__ import annotations

import argparse

from grafana_tool.cli_common import add_write_options
from grafana_tool.io import load_dashboard
from grafana_tool.model import (
    append_to_row_block,
    find_panel_container,
    find_row,
    row_children,
)
from grafana_tool.persist import save_and_validate

NAME = "move-panel"
HELP = "Sposta un pannello in un'altra riga"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--panel-id", type=int, required=True, help="ID del pannello da spostare")
    parser.add_argument("--target-row", type=int, required=True, help="ID della riga di destinazione")
    add_write_options(parser)

def run(args: argparse.Namespace) -> int:
    db = load_dashboard(args.file)

    container, idx = find_panel_container(db, args.panel_id)
    if container is None:
        raise ValueError(f"Pannello {args.panel_id} non trovato.")
    panel = container[idx]
    if panel.get("type") == "row":
        raise ValueError("move-panel non sposta righe; usare --panel-id di un pannello.")

    tgt = find_row(db, args.target_row)
    if tgt is None:
        raise ValueError(f"Riga {args.target_row} non trovata.")
    if any(
        isinstance(p, dict) and p.get("id") == args.panel_id
        for p in row_children(db, tgt)
    ):
        raise ValueError(f"Il pannello {args.panel_id} è già nella riga {args.target_row}.")

    del container[idx]
    append_to_row_block(db, tgt, panel)

    print(f"Pannello {args.panel_id} spostato nella riga {args.target_row}.")
    return save_and_validate(db, args)
