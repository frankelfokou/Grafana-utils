"""lint: esegue il linter di best practice sulla dashboard."""
from __future__ import annotations

import argparse
import json
import sys

from grafana_tool import errors, validation
from grafana_tool.cli_common import add_format_option, add_severity_option
from grafana_tool.command_base import ReadCommand
from grafana_tool.linter import lint


class LintCommand(ReadCommand):
    NAME = "lint"
    HELP = "Esegue il linter di best practice"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_format_option(parser)
        add_severity_option(
            parser, "Exit 1 se almeno una issue è >= soglia (default: error)"
        )

    def perform(self, db: dict, args: argparse.Namespace) -> int:
        issues = lint(db)
        blocking = validation.blocking_issues(issues, args.severity)

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
            details=validation.issue_lines(blocking),
        )
        if log:
            stream = sys.stderr if args.format == "json" else sys.stdout
            print(f"Log: {log}", file=stream)
        return 1


command = LintCommand()

