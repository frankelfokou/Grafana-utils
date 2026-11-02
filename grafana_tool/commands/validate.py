"""validate: valida struttura e qualità della dashboard.

È l'operazione finale della pipeline di scrittura: `persist.save_and_validate`
usa lo stesso codice, quindi l'esito è identico. Il comando è read-only sulla
dashboard, ma in caso di fallimento registra il report in `out/`.
"""
from __future__ import annotations

import argparse

from grafana_tool import errors, validation
from grafana_tool.io import load_dashboard

NAME = "validate"
HELP = "Valida struttura e lint della dashboard"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--severity", choices=["info", "warning", "error"],
                        default="error",
                        help="Soglia che fa fallire la validazione (default: error)")

def run(args: argparse.Namespace) -> int:
    db = load_dashboard(args.file)
    result = validation.check(db, args.severity)

    print(f"Dashboard: {validation.summary(db)}")
    for line in validation.render(result):
        print(line)

    if not result.failing:
        return 0

    kind = result.kind or "validation"
    log = errors.log_error(
        kind,
        f"validazione fallita: {args.file}",
        command="validate",
        exit_code=1,
        details=result.errors
        + [f"[{i.code}] {i.severity}: {i.message}" for i in result.blocking],
    )
    if log:
        print(f"Log: {log}")
    return 1
