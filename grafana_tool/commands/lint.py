"""lint: esegue il linter di best practice sulla dashboard."""
from __future__ import annotations

import argparse
import json
import sys

from grafana_tool import errors, validation
from grafana_tool.io import load_dashboard
from grafana_tool.linter import lint

NAME = "lint"
HELP = "Esegue il linter di best practice"

def configure(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("file", help="Percorso del file dashboard JSON (deve esistere)")
    parser.add_argument("--format", choices=["text", "json"], default="text",
                        help="Formato di output (default: text)")
    parser.add_argument("--severity", choices=["info", "warning", "error"],
                        default="error",
                        help="Exit 1 se almeno una issue è >= soglia (default: error)")

def run(args: argparse.Namespace) -> int:
    db = load_dashboard(args.file)
    issues = lint(db)
    limit = validation.SEV_ORDER[args.severity]
    blocking = [i for i in issues if validation.SEV_ORDER[i.severity] >= limit]

    if args.format == "json":
        print(json.dumps([i.as_dict() for i in issues], indent=2, ensure_ascii=False))
    elif not issues:
        print("Nessuna issue trovata.")
    else:
        for i in issues:
            print(f"{validation.SEV_LABEL[i.severity]} [{i.code}] {i.message}")
        print(f"\nTotale: {len(issues)} issue ({len(blocking)} >= {args.severity}).")

    if not blocking:
        return 0

    log = errors.log_error(
        "lint",
        f"{len(blocking)} issue >= {args.severity}",
        command="lint",
        exit_code=1,
        details=[f"[{i.code}] {i.severity}: {i.message}" for i in blocking],
    )
    if log:
        stream = sys.stderr if args.format == "json" else sys.stdout
        print(f"Log: {log}", file=stream)
    return 1
