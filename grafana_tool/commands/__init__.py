"""Registro dei sottocomandi.

Il blocco CRUD è unificato: `list`, `create`, `update`, `delete`, `move`
ed `extract` ricevono `row` o `panel` come primo argomento, quindi non
esiste più un comando per tipo di oggetto.

Ogni modulo espone `command`: un'istanza di `ReadCommand` o `WriteCommand`
con l'interfaccia uniforme usata da `cli.py`:

    NAME       stringa
    HELP       stringa
    configure(parser)  aggiunge gli argomenti
    run(args)          esegue e ritorna un exit code (int)

L'ordine di `ALL_COMMANDS` è l'ordine in cui i comandi compaiono nell'help.
"""
from .create import command as create
from .delete import command as delete
from .extract import command as extract
from .layout import command as layout
from .lint import command as lint
from .list import command as list_
from .move import command as move
from .update import command as update
from .validate import command as validate

ALL_COMMANDS = [
    list_,
    create,
    update,
    delete,
    move,
    extract,
    layout,
    validate,
    lint,
]

