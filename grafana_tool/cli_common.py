"""Responsabilità unica: opzioni CLI comuni ai comandi di scrittura.

Centralizza i flag condivisi da tutti i comandi che modificano e salvano
la dashboard, incluso il contratto I/O e la validazione finale.
"""
from __future__ import annotations

import argparse


def add_write_options(parser: argparse.ArgumentParser) -> None:
    """Aggiunge a `parser` le opzioni comuni dei comandi di scrittura:

    -o/--output, --dry-run, --lint-severity.

    Contratto I/O:
      - il file di input (argomento posizionale `file`) non viene MAI
        modificato;
      - senza -o il risultato va in `<input>_out.json` (stessa directory);
      - con -o il risultato va nel path indicato;
      - se la validazione finale fallisce, al nome viene appeso
        `_ERROR_<TIPO>` e il report finisce in `out/`.
    """
    parser.add_argument(
        "-o", "--output", metavar="FILE",
        help=(
            "File JSON di output. Se omesso: <input>_out.json. "
            "Il file di input non viene mai sovrascritto."
        ),
    )
    parser.add_argument("--dry-run", action="store_true",
                        help="Non scrive il file (la validazione gira comunque in memoria)")
    parser.add_argument("--lint-severity", choices=["info", "warning", "error"],
                        default="error",
                        help="Soglia che fa fallire la validazione finale (default: error)")


def add_title_options(parser: argparse.ArgumentParser) -> None:
    """Aggiunge `--dedupe-titles` ai comandi che creano righe o pannelli.

    Il default è conservativo: i titoli degli oggetti creati restano identici
    alla sorgente. Con il flag vengono disambiguati rispetto ai titoli già
    presenti nella dashboard, con il suffisso ` (2)`, ` (3)`.
    """
    parser.add_argument(
        "--dedupe-titles", action="store_true",
        help=(
            "Rendi unici i titoli degli oggetti creati: se il nome esiste già "
            "nella dashboard aggiunge il suffisso (2), (3)"
        ),
    )
