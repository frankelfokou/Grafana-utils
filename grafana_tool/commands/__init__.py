"""Registro dei sottocomandi.

Ogni comando espone l'interfaccia uniforme:
    NAME       stringa
    HELP       stringa
    configure(parser)  aggiunge gli argomenti
    run(args)          esegue e ritorna un exit code (int)

I comandi possono essere implementati come moduli con funzioni (stile
storico) o come istanze di `grafana_tool.command_base.WriteCommand` (stile
class-based, Template Method). Entrambi i pattern sono accettati da cli.py.
"""
from . import (
    copy_panel,
    duplicate_row,
    lint,
    list_panels,
    list_rows,
    move_panel,
    prune,
    reflow,
    replace,
    set_datasource,
    transform,
    validate,
)
from .append_row import command as append_row
from .extract_row import command as extract_row

ALL_COMMANDS = [
    list_rows,
    list_panels,
    duplicate_row,
    copy_panel,
    move_panel,
    replace,
    transform,
    prune,
    set_datasource,
    reflow,
    validate,
    lint,
    append_row,
    extract_row,
]
