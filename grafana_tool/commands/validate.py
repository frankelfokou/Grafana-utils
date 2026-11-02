"""validate: valida struttura e qualità della dashboard.

È l'operazione finale della pipeline di scrittura: `persist.save_and_validate`
usa lo stesso codice, quindi l'esito è identico. Il comando è read-only sulla
dashboard, ma in caso di fallimento registra il report in `out/`.
"""
from __future__ import annotations

import argparse

from grafana_tool import errors, validation
from grafana_tool.cli_common import add_severity_option
from grafana_tool.command_base import ReadCommand


class ValidateCommand(ReadCommand):
    NAME = "validate"
    HELP = "Valida struttura e lint della dashboard"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_severity_option(
            parser, "Soglia che fa fallire la validazione (default: error)"
        )

    def perform(self, db: dict, args: argparse.Namespace) -> int:
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
            details=validation.failure_details(result),
        )
        if log:
            print(f"Log: {log}")
        return 1


command = ValidateCommand()

