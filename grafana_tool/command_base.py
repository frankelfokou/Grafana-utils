"""command_base: WriteCommand — Template Method per comandi di scrittura.

Fornisce la classe base astratta `WriteCommand` che incapsula lo scheletro
comune a tutti i comandi di scrittura:

    1. carica il dashboard di input (input mai modificato);
    2. chiama il metodo astratto `modify` per la logica specifica;
    3. salva e valida tramite `persist.save_and_validate`.

I comandi concreti ereditano da `WriteCommand` e implementano solo `modify`
e `configure`. Questo elimina il boilerplate ripetuto in ogni modulo
comando e centralizza il contratto I/O in un unico punto.

Le istanze di `WriteCommand` sono direttamente registrabili in
`commands/__init__.py` come elementi di `ALL_COMMANDS`, perché espongono
`NAME`, `HELP`, `configure(parser)` e `run(args)` con la stessa interfaccia
dei moduli comando esistenti.
"""
from __future__ import annotations

import argparse
import copy
from typing import Any

from grafana_tool.cli_common import add_write_options
from grafana_tool.io import load_dashboard
from grafana_tool.persist import save_and_validate


class WriteCommand:
    """Classe base per comandi di scrittura (Template Method).

    Attributi di classe:
        NAME  — nome del subparser
        HELP  — testo descrittivo per la lista comandi
    """

    NAME: str = ""
    HELP: str = ""

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Aggiunge gli argomenti specifici e le opzioni comuni di scrittura."""
        add_write_options(parser)

    def modify(self, db: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
        """Applica la trasformazione specifica al dashboard in memoria.

        Riceve una copia profonda del dashboard; può modificarlo e restituirlo.
        Il metodo base restituisce il dashboard invariato.
        """
        return db

    def run(self, args: argparse.Namespace) -> int:
        """Template method: load → modify → save_and_validate."""
        db = load_dashboard(args.file)
        db = copy.deepcopy(db)
        db = self.modify(db, args)
        return save_and_validate(db, args)
