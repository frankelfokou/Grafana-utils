"""transform: applica trasformazioni a pannelli che matchano criteri."""
from __future__ import annotations

import argparse
import json
from typing import Any

from grafana_tool.cli_common import add_write_options
from grafana_tool.io import load_dashboard
from grafana_tool.model import iter_content_panels, title_regex
from grafana_tool.persist import save_and_validate
from grafana_tool.replacements import apply_in_panel, parse_replacements

NAME = "transform"
HELP = "Applica trasformazioni a pannelli che matchano --match-type/--match-title"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--match-type", help="Filtra per tipo (es. graph, timeseries)")
    parser.add_argument("--match-title", help="Filtra per titolo (regex)")
    parser.add_argument("--replace", action="append", default=[], metavar="OLD=NEW",
                        help="Sostituzione su target[*].expr (ripetibile)")
    parser.add_argument("--ds-uid", dest="ds_uid", help="Imposta uid datasource")
    parser.add_argument("--ds-type", help="Imposta type datasource (con --ds-uid)")
    parser.add_argument("--new-title", help="Sovrascrive il titolo dei pannelli matchati")
    add_write_options(parser)

def _set_datasource(container: dict[str, Any], uid: str, ds_type: str | None) -> None:
    ds = container.get("datasource")
    if isinstance(ds, dict):
        ds["uid"] = uid
        if ds_type:
            ds["type"] = ds_type
    else:
        container["datasource"] = {"type": ds_type or "prometheus", "uid": uid}

def run(args: argparse.Namespace) -> int:
    if not (args.match_type or args.match_title):
        raise ValueError("Specificare almeno --match-type o --match-title.")
    db = load_dashboard(args.file)
    title_re = title_regex(args.match_title) if args.match_title else None
    repl = parse_replacements(args.replace)

    matched = 0
    modified = 0
    for p in iter_content_panels(db):
        if args.match_type and str(p.get("type") or "").casefold() != args.match_type.casefold():
            continue
        if title_re and not title_re.search(p.get("title") or ""):
            continue
        matched += 1
        before = json.dumps(p, sort_keys=True, default=str)

        if repl:
            apply_in_panel(p, repl)
        if args.ds_uid:
            _set_datasource(p, args.ds_uid, args.ds_type)
            for t in p.get("targets") or []:
                if isinstance(t, dict):
                    _set_datasource(t, args.ds_uid, args.ds_type)
        if args.new_title:
            p["title"] = args.new_title

        if json.dumps(p, sort_keys=True, default=str) != before:
            modified += 1

    print(f"Pannelli corrispondenti: {matched}. Modificati: {modified}.")
    return save_and_validate(db, args)
