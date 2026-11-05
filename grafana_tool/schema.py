"""schema: riconoscere il formato della dashboard e gestirne i metadati.

Il tool manipola il **JSON model classico**, dove righe e pannelli stanno in
liste (`panels` / `rows`), ogni oggetto ha un `id` intero e la posizione è in
`gridPos`.

Il **nuovo schema** (`elements` + `layout`) descrive la stessa dashboard in
modo diverso: i pannelli stanno in una mappa indicizzata per nome, le righe
sono nodi di un albero di layout, e non esistono id di riga, `targets` o
`templating`. Applicare al secondo gli attraversamenti del primo non produce
un errore: produce zero righe e zero pannelli. Per questo il formato viene
riconosciuto prima di ogni operazione.

Questo modulo si occupa solo di:

  - riconoscere il formato (`detect`) e rifiutare l'irriconoscibile;
  - aggiungere i metadati di servizio che il modello canonico usa per i tab
    e per i nomi degli elementi;
  - rimuovere quei metadati prima di scrivere il file.

La conversione vera e propria vive nel package `grafana_tool.formats`.
"""
from __future__ import annotations

from typing import Any

from grafana_tool.io import InputError
from grafana_tool.model import iter_all_panels, iter_rows

CLASSIC = "classic"
V2 = "v2"
UNKNOWN = "unknown"

# Tab implicito di una dashboard classica, che non conosce i tab.
IMPLICIT_TAB_ID = 1

# Chiavi di servizio del modello canonico. Non si usa un prefisso generico
# perché il JSON di Grafana contiene già chiavi come `__systemRef`.
INTERNAL_KEYS = frozenset({"_tabs", "_tab", "_element", "_extras"})


def detect(db: dict[str, Any]) -> str:
    """Riconosce il formato di una dashboard già caricata."""
    if isinstance(db.get("elements"), dict) and isinstance(db.get("layout"), dict):
        return V2
    if isinstance(db.get("panels"), list) or isinstance(db.get("rows"), list):
        return CLASSIC
    return UNKNOWN


def describe(kind: str) -> str:
    """Descrizione leggibile del formato."""
    if kind == V2:
        return "schema v2 ('elements' + 'layout')"
    if kind == CLASSIC:
        return "JSON model classico ('panels'/'rows')"
    return "formato non riconosciuto"


def require_recognized(db: dict[str, Any], *, command: str = "") -> str:
    """Ritorna il formato, oppure solleva `InputError` se non è riconoscibile.

    Un documento senza marcatori non è una dashboard vuota: è un formato che
    il tool non sa interpretare. Trattarlo come classico produrrebbe report
    di validazione verdi su un file mai letto.
    """
    kind = detect(db)
    if kind == UNKNOWN:
        where = f" ({command})" if command else ""
        raise InputError(
            f"formato non riconosciuto{where}: il file non contiene né "
            "'panels'/'rows' (JSON model classico) né 'elements' + 'layout' "
            "(schema v2)."
        )
    return kind


def ensure_tabs(db: dict[str, Any], *, title: "str | None" = None) -> None:
    """Aggiunge il tab implicito a una dashboard classica (idempotente).

    Il modello canonico ha sempre almeno un tab, così `list tab` e i comandi
    sui tab funzionano anche sui file classici, che i tab non li hanno.
    Il titolo predefinito è quello della dashboard: convertita in v2, una
    dashboard classica deve mostrare qualcosa di leggibile nella barra dei tab.
    """
    if isinstance(db.get("_tabs"), list) and db["_tabs"]:
        return
    if title is None:
        title = db.get("title") or ""
    db["_tabs"] = [{"id": IMPLICIT_TAB_ID, "title": title}]
    for row in iter_rows(db):
        row.setdefault("_tab", IMPLICIT_TAB_ID)


def canonical_tabs(db: dict[str, Any]) -> list[dict[str, Any]]:
    """Tab del modello canonico (lista, mai None)."""
    tabs = db.get("_tabs")
    return tabs if isinstance(tabs, list) else []


def tab_of(row: dict[str, Any]) -> int:
    """Id del tab di appartenenza di una riga."""
    value = row.get("_tab", IMPLICIT_TAB_ID)
    return value if isinstance(value, int) else IMPLICIT_TAB_ID


def strip_internal(db: dict[str, Any]) -> None:
    """Rimuove le chiavi di servizio prima di serializzare la dashboard."""
    for key in INTERNAL_KEYS:
        db.pop(key, None)
    for panel in iter_all_panels(db):
        for key in INTERNAL_KEYS:
            panel.pop(key, None)
