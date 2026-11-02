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

from grafana_tool import errors, io, validation


def resolve_output(args: argparse.Namespace) -> str:
    """Path di output: quello esplicito oppure `<input>_out.json`."""
    return getattr(args, "output", None) or io.default_output_path(args.file)


def save_and_validate(db: dict[str, Any], args: argparse.Namespace) -> int:
    """Salva `db` e applica la validazione finale.

    Ritorna 0 se la validazione passa, 1 se fallisce.
    """
    out = resolve_output(args)
    dry_run = bool(getattr(args, "dry_run", False))
    threshold = getattr(args, "severity", "error")

    io.save_dashboard(db, out, dry_run=dry_run)

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
