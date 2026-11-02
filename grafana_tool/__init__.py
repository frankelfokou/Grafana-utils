"""grafana_tool — CLI modulare per manipolare dashboard Grafana (JSON).

Struttura del pacchetto:
    io.py            → load/save del file JSON + InputError/OutputError
    model.py         → traversal della dashboard (righe, pannelli, ID)
    replacements.py  → parsing e applicazione delle sostituzioni
    placeholders.py  → sostituzione ricorsiva ${CHIAVE}
    identity.py      → uid, titoli unici e id dei pannelli
    linter.py        → regole e engine di linting
    validation.py    → validazione struttura + lint (condivisa)
    errors.py        → tipi di errore, suffissi e log in out/
    persist.py       → pipeline "salva + valida"
    cli_common.py    → opzioni CLI condivise dai comandi di scrittura
    commands/        → un modulo per ogni sottocomando
    cli.py           → argparse + dispatch + exit code
    __main__.py      → entry point per `python -m grafana_tool`
"""

__version__ = "5.0.0"
