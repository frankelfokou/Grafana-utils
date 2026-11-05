"""Responsabilità unica: pipeline "salva + valida".

Ogni comando di scrittura chiama `save_and_validate(db, args)`.
La pipeline:

  1. risolve il file di output (`-o`, altrimenti `<input>_out.json`);
  2. scrive il file senza mai toccare l'input;
  3. esegue la validazione finale (struttura + lint) sull'oggetto salvato;
  4. se la validazione fallisce, rinomina il file appendendo
     `_ERROR_<TIPO>` e registra il log in `out/`;
  5. restituisce l'exit code (0 oppure 1).

Il modulo è l'unico punto in cui I/O, validazione e log si incontrano.
"""
from __future__ import annotations

import argparse
import os
from typing import Any

from grafana_tool import errors, formats, io, validation


def resolve_output(args: argparse.Namespace) -> str:
    """Path di output: quello esplicito oppure `<input>_out.json`."""
    return getattr(args, "output", None) or io.default_output_path(args.file)


def resolve_target_format(
    args: argparse.Namespace, loaded: "formats.Loaded | None"
) -> str:
    """Formato di uscita: `--to-format` oppure quello del file di ingresso."""
    explicit = getattr(args, "to_format", None)
    if explicit:
        return explicit
    if loaded is not None:
        return loaded.target_default
    return "classic"


def _print_report(report: "formats.Report") -> None:
    """Stampa le perdite dichiarate dalla conversione di uscita."""
    for line in report.lines():
        print(line)


def save_and_validate(
    db: dict[str, Any],
    args: argparse.Namespace,
    loaded: "formats.Loaded | None" = None,
) -> int:
    """Salva `db` e applica la validazione finale.

    `db` è il modello canonico: viene convertito nel formato di uscita
    (`--to-format`, altrimenti lo stesso dell'ingresso) solo qui, all'ultimo
    passaggio. La validazione gira sul canonico, così è identica per entrambi
    i formati. Ritorna 0 se la validazione passa, 1 se fallisce.
    """
    out = resolve_output(args)
    dry_run = bool(getattr(args, "dry_run", False))
    threshold = getattr(args, "severity", "error")

    document, report = formats.render(
        db,
        getattr(args, "target_format", None) or resolve_target_format(args, loaded),
        drop_alerts=bool(getattr(args, "drop_alerts", False)),
        keep_variable_visibility=bool(getattr(args, "keep_variable_visibility", False)),
        keep_literal_values=bool(getattr(args, "keep_literal_values", False)),
    )
    io.save_dashboard(document, out, dry_run=dry_run)
    _print_report(report)

    result = validation.check(db, threshold)
    print()
    for line in validation.render(result):
        print(line)

    if not result.failing:
        return 0

    kind = result.kind or "validation"
    if dry_run:
        candidate = io.with_suffix(out, errors.suffix(kind))
        print(f"[dry-run] Con questi errori il file sarebbe: {candidate}")
        return 1

    final = os.path.abspath(io.with_suffix(out, errors.suffix(kind)))
    renamed = True
    try:
        os.replace(out, final)
    except OSError:
        renamed = False

    log = errors.log_error(
        kind,
        f"validazione fallita per {os.path.basename(out)}",
        command=getattr(args, "cmd", None),
        exit_code=1,
        details=validation.failure_details(result),
    )

    if renamed:
        print(f"Validazione fallita ({kind}): file rinominato in {final}")
    else:
        print(f"Validazione fallita ({kind}): impossibile rinominare {out}")
    if log:
        print(f"   Log: {log}")
    return 1
