"""set-datasource: cambia l'UID del datasource nei pannelli e nei target."""
from __future__ import annotations

import argparse
from typing import Any

from grafana_tool.cli_common import add_write_options
from grafana_tool.io import load_dashboard
from grafana_tool.model import collect_scope
from grafana_tool.persist import save_and_validate

NAME = "set-datasource"
HELP = "Cambia l'UID del datasource nei pannelli/target"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--uid", required=True, help="Nuovo datasource UID")
    parser.add_argument("--type", help="Nuovo datasource type (es. prometheus)")
    parser.add_argument("--row", type=int, help="Limita alla riga con questo ID")
    parser.add_argument("--force", action="store_true",
                        help="Crea il blocco datasource se assente (default: skip)")
    add_write_options(parser)

def _update_ds(container: dict[str, Any], uid: str, ds_type: str | None, force: bool) -> int:
    """Aggiorna il blocco `datasource` di un pannello/target. Ritorna 1 se ha modificato."""
    ds = container.get("datasource")
    if isinstance(ds, dict):
        ds["uid"] = uid
        if ds_type:
            ds["type"] = ds_type
        return 1
    if force:
        container["datasource"] = {"type": ds_type or "prometheus", "uid": uid}
        return 1
    return 0

def run(args: argparse.Namespace) -> int:
    db = load_dashboard(args.file)
    panels = collect_scope(db, args.row)
    total = 0
    for p in panels:
        total += _update_ds(p, args.uid, args.type, args.force)
        for t in p.get("targets") or []:
            if isinstance(t, dict):
                total += _update_ds(t, args.uid, args.type, args.force)
    print(f"Datasource aggiornato in {total} punti.")
    return save_and_validate(db, args)
