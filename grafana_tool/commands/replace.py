"""replace: sostituzioni testuali globali nelle query."""
from __future__ import annotations

import argparse

from grafana_tool.cli_common import add_write_options
from grafana_tool.io import load_dashboard
from grafana_tool.model import collect_scope
from grafana_tool.persist import save_and_validate
from grafana_tool.replacements import apply_in_panel, parse_replacements

NAME = "replace"
HELP = "Sostituzioni testuali globali nei target[*].expr"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--replace", action="append", required=True, metavar="OLD=NEW",
                        help="Sostituzione OLD=NEW (ripetibile)")
    parser.add_argument("--row", type=int, help="Limita alla riga con questo ID")
    add_write_options(parser)

def run(args: argparse.Namespace) -> int:
    db = load_dashboard(args.file)
    repl = parse_replacements(args.replace)
    panels = collect_scope(db, args.row)
    total = sum(apply_in_panel(p, repl) for p in panels)
    print(f"Sostituzioni applicate a {total} target.")
    return save_and_validate(db, args)
