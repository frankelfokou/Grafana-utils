"""command_base: classi base dei comandi (Template Method).

Tutti i sottocomandi sono istanze di una di queste classi, così lo scheletro
comune vive in un solo posto:

    BaseCommand   — contratto uniforme (NAME, HELP, configure, run)
      ReadCommand — carica la dashboard e chiama `perform` (nessuna scrittura)
      WriteCommand — carica una copia, chiama `modify`, poi `save_and_validate`

I comandi concreti implementano solo gli hook:

    add_arguments(parser)   opzioni specifiche del comando
    perform(db, args)       logica dei comandi read-only
    modify(db, args)        trasformazione dei comandi di scrittura

Vantaggio: input mai modificato, deep-copy, salvataggio e validazione finale
esistono una volta sola; per cambiare il contratto I/O si tocca questo file.
"""
from __future__ import annotations

import argparse
import copy
from typing import Any

from grafana_tool.cli_common import add_file_argument, add_write_options
from grafana_tool.io import load_dashboard
from grafana_tool.persist import save_and_validate


class BaseCommand:
    """Contratto uniforme dei sottocomandi.

    Attributi di classe:
        NAME  — nome del subparser
        HELP  — testo descrittivo per la lista comandi
    """

    NAME: str = ""
    HELP: str = ""

    def configure(self, parser: argparse.ArgumentParser) -> None:
        """Aggiunge le opzioni specifiche e poi quelle comuni della famiglia.

        I comandi concreti non ridefiniscono questo metodo: implementano
        `add_arguments`, così ordine e presenza delle opzioni comuni
        restano uniformi.
        """
        self.add_arguments(parser)
        self.add_common_options(parser)

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        """Hook: opzioni specifiche del comando."""

    def add_common_options(self, parser: argparse.ArgumentParser) -> None:
        """Hook: opzioni comuni alla famiglia del comando."""

    def run(self, args: argparse.Namespace) -> int | None:
        """Esegue il comando. Le sottoclassi ridefiniscono questo metodo."""
        raise NotImplementedError


class ReadCommand(BaseCommand):
    """Comando che legge la dashboard senza produrre un file di output."""

    def add_common_options(self, parser: argparse.ArgumentParser) -> None:
        add_file_argument(parser)

    def perform(self, db: dict[str, Any], args: argparse.Namespace) -> int | None:
        """Hook: logica del comando sulla dashboard già caricata."""
        raise NotImplementedError

    def run(self, args: argparse.Namespace) -> int | None:
        """Template method: load → perform."""
        return self.perform(load_dashboard(args.file), args)


class WriteCommand(BaseCommand):
    """Comando che modifica la dashboard e produce un file di output."""

    def add_common_options(self, parser: argparse.ArgumentParser) -> None:
        add_file_argument(parser)
        add_write_options(parser)

    def modify(self, db: dict[str, Any], args: argparse.Namespace) -> dict[str, Any]:
        """Hook: applica la trasformazione specifica al dashboard in memoria.

        Riceve una copia profonda del dashboard; può modificarlo e restituirlo.
        Il metodo base restituisce il dashboard invariato.
        """
        return db

    def report_renamed(self, count: int) -> None:
        """Messaggio unico per i titoli disambiguati da `--dedupe-titles`."""
        if count:
            print(f"Titoli pannelli disambiguati: {count}.")

    def run(self, args: argparse.Namespace) -> int:
        """Template method: load → deep-copy → modify → save_and_validate."""
        db = copy.deepcopy(load_dashboard(args.file))
        db = self.modify(db, args)
        return save_and_validate(db, args)
