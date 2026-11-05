"""Responsabilità unica: opzioni CLI comuni ai comandi.

Centralizza i flag condivisi da più comandi, così testo, default e
`choices` esistono in un solo posto. Nessun comando ridefinisce a mano
un'opzione che vive qui.

Vocabolario delle opzioni, uguale per tutti i comandi che agiscono su un
oggetto:

  - **tipo**: argomento posizionale `row`, `panel` oppure `tab`;
  - **selettori** (`--id`, `--match-title`, `--match-type`, `--in-row`,
    `--in-tab`): scelgono *quali* oggetti;
  - **impostazioni** (`--title`, `--collapsed`, `--replace`, `--datasource`):
    dicono *cosa* cambiare.

La regola mnemonica è: `--match-*` seleziona, le altre opzioni impostano.
"""
from __future__ import annotations

import argparse

FILE_HELP = "Percorso del file dashboard JSON (deve esistere)"
SEVERITY_CHOICES = ("info", "warning", "error")
KIND_CHOICES = ("row", "panel", "tab")
FORMAT_CHOICES = ("text", "json")
TO_FORMAT_CHOICES = ("classic", "v2")


def add_file_argument(parser: argparse.ArgumentParser) -> None:
    """Aggiunge l'argomento posizionale `file` (dashboard di input)."""
    parser.add_argument("file", help=FILE_HELP)


def add_kind_argument(parser: argparse.ArgumentParser) -> None:
    """Aggiunge il tipo di oggetto: `row`, `panel` oppure `tab`."""
    parser.add_argument(
        "kind", choices=list(KIND_CHOICES), metavar="{row,panel,tab}",
        help=(
            "Tipo di oggetto su cui operare: row (riga), panel (pannello) "
            "o tab (scheda)"
        ),
    )


def add_severity_option(parser: argparse.ArgumentParser, help: str) -> None:
    """Aggiunge `--severity`, la soglia di severità usata da validate/lint."""
    parser.add_argument(
        "--severity", choices=list(SEVERITY_CHOICES), default="error", help=help
    )


def add_format_option(parser: argparse.ArgumentParser) -> None:
    """Aggiunge `--format text|json` ai comandi che stampano un elenco."""
    parser.add_argument(
        "--format", choices=list(FORMAT_CHOICES), default="text",
        help="Formato di output (default: text)",
    )


def add_write_options(parser: argparse.ArgumentParser) -> None:
    """Aggiunge a `parser` le opzioni comuni dei comandi di scrittura:

    -o/--output, --dry-run, --severity.

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
    add_to_format_option(parser)
    parser.add_argument(
        "--drop-alerts", dest="drop_alerts", action="store_true",
        help=(
            "Permette l'uscita v2 scartando le regole di alert legacy dei pannelli "
            "(senza il flag la conversione si ferma)"
        ),
    )
    parser.add_argument(
        "--keep-variable-visibility", dest="keep_variable_visibility",
        action="store_true",
        help=(
            "Non rendere visibili le variabili in alto: conserva il `hide` "
            "della dashboard di origine"
        ),
    )
    parser.add_argument(
        "--keep-literal-values", dest="keep_literal_values", action="store_true",
        help=(
            "Non sostituire con $variabile i valori fissi delle query che "
            "hanno il nome di una variabile"
        ),
    )
    add_severity_option(
        parser, "Soglia che fa fallire la validazione finale (default: error)"
    )


def add_to_format_option(parser: argparse.ArgumentParser) -> None:
    """Aggiunge `--to-format`, il formato del file di output.

    Se omesso vale il formato del file di ingresso: convertire è una scelta
    esplicita, non un effetto collaterale.
    """
    parser.add_argument(
        "--to-format", dest="to_format", choices=list(TO_FORMAT_CHOICES),
        help=(
            "Formato del file di output: classic (panels/rows) o v2 "
            "(elements/layout). Default: lo stesso dell'ingresso"
        ),
    )


def add_selectors(parser: argparse.ArgumentParser) -> None:
    """Aggiunge i selettori comuni: chi viene toccato dal comando.

    Gli stessi quattro selettori valgono per righe e pannelli; quelli che non
    hanno senso per il tipo scelto vengono rifiutati a runtime con un
    messaggio esplicito.
    """
    parser.add_argument(
        "--id", type=int, action="append", default=[], metavar="N",
        help="Seleziona l'oggetto con questo id (ripetibile)",
    )
    parser.add_argument(
        "--match-title", metavar="REGEX",
        help="Seleziona gli oggetti con titolo che matcha la regex (case-insensitive)",
    )
    parser.add_argument(
        "--match-type", metavar="TIPO",
        help="Seleziona i pannelli di questo tipo (es. timeseries)",
    )
    parser.add_argument(
        "--in-row", type=int, metavar="N",
        help="Limita ai pannelli della riga con questo id",
    )
    parser.add_argument(
        "--in-tab", dest="in_tab", type=int, metavar="N",
        help="Limita alle righe (o ai pannelli) del tab con questo id",
    )


def add_to_tab_option(parser: argparse.ArgumentParser) -> None:
    """Aggiunge `--to-tab` (e l'alias `--tab`): tab di destinazione.

    Vale per le righe: in `create row` è il tab in cui nasce la riga
    (default: il primo), in `move row` quello in cui si trasferisce.
    """
    parser.add_argument(
        "--to-tab", "--tab", dest="to_tab", type=int, metavar="N",
        help="Tab di destinazione della riga (default: il primo tab)",
    )


def add_title_option(
    parser: argparse.ArgumentParser, help: str = "Nuovo titolo dell'oggetto"
) -> None:
    """Aggiunge `--title` (imposta il titolo, non seleziona)."""
    parser.add_argument("--title", help=help)


def add_collapsed_options(
    parser: argparse.ArgumentParser, *, default: bool | None = None
) -> None:
    """Aggiunge `--collapsed` / `--expanded` per lo stato di una riga."""
    parser.add_argument(
        "--collapsed", dest="collapsed", action="store_true", default=default,
        help="Rendi la riga collassata",
    )
    parser.add_argument(
        "--expanded", dest="collapsed", action="store_false",
        help="Rendi la riga espansa (figli top-level subito dopo)",
    )


def add_replace_option(parser: argparse.ArgumentParser, help: str) -> None:
    """Aggiunge `--replace OLD=NEW`, ripetibile."""
    parser.add_argument(
        "--replace", action="append", default=[], metavar="OLD=NEW", help=help
    )


def add_datasource_options(parser: argparse.ArgumentParser) -> None:
    """Aggiunge le opzioni che agiscono sul blocco datasource."""
    parser.add_argument("--datasource", metavar="UID",
                        help="Imposta datasource.uid di pannelli e target")
    parser.add_argument("--datasource-type", dest="datasource_type", metavar="TIPO",
                        help="Imposta anche datasource.type (es. prometheus)")
    parser.add_argument("--datasource-create", dest="datasource_create",
                        action="store_true",
                        help="Crea il blocco datasource quando è assente")


def add_dedupe_option(parser: argparse.ArgumentParser) -> None:
    """Aggiunge `--dedupe-titles` ai comandi che creano o rinominano oggetti.

    Il default è conservativo: i titoli degli oggetti creati restano identici
    alla sorgente. Con il flag vengono disambiguati rispetto ai titoli già
    presenti nella dashboard, con il suffisso ` (2)`, ` (3)`.
    """
    parser.add_argument(
        "--dedupe-titles", action="store_true",
        help=(
            "Rendi unico il titolo degli oggetti creati o rinominati: se il nome "
            "esiste già nella dashboard aggiunge il suffisso (2), (3)"
        ),
    )
