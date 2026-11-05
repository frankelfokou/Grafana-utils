"""tabs: i tab della dashboard come contenitori di primo livello.

Nel JSON classico un tab non esiste: la dashboard ha righe e pannelli. Il
modello canonico lo introduce come contenitore logico, con due sole tracce:

  - `db["_tabs"]` elenca i tab, `[{"id": 1, "title": "..."}]`;
  - ogni riga dichiara il proprio tab in `row["_tab"]`.

Un pannello non ha un tab proprio: appartiene a quello della riga che lo
contiene. I pannelli che non stanno in nessuna riga sono del primo tab.

Il modulo è puro: nessun argparse, nessun I/O. `objects.py` lo usa per
esporre i tab dietro lo stesso `Target` di righe e pannelli.
"""
from __future__ import annotations

from typing import Any, Iterable

from grafana_tool import schema
from grafana_tool.model import iter_panel_slots, iter_rows, remove_row_block, row_children


def all_tabs(db: dict[str, Any]) -> list[dict[str, Any]]:
    """Tab della dashboard, creando quello implicito se manca."""
    schema.ensure_tabs(db)
    return schema.canonical_tabs(db)


def find(db: dict[str, Any], tab_id: Any) -> dict[str, Any] | None:
    """Tab con quell'id, oppure `None`."""
    for tab in all_tabs(db):
        if tab.get("id") == tab_id:
            return tab
    return None


def describe_available(db: dict[str, Any]) -> str:
    """Elenco leggibile dei tab esistenti, per i messaggi d'errore."""
    tabs = all_tabs(db)
    return ", ".join(
        f"{tab.get('id')} ('{tab.get('title') or ''}')" for tab in tabs
    ) or "nessuno"


def require(db: dict[str, Any], tab_id: Any, *, where: str = "") -> dict[str, Any]:
    """Tab con quell'id; solleva `ValueError` se non esiste."""
    tab = find(db, tab_id)
    if tab is None:
        raise ValueError(
            f"Tab {tab_id} non trovato. Tab disponibili: {describe_available(db)}."
        )
    return tab


def next_id(db: dict[str, Any]) -> int:
    """Primo id libero per un nuovo tab."""
    ids = [
        tab["id"] for tab in all_tabs(db)
        if isinstance(tab.get("id"), int)
    ]
    return max(ids + [0]) + 1


def first_id(db: dict[str, Any]) -> int:
    """Id del primo tab, quello che accoglie le righe senza destinazione."""
    return all_tabs(db)[0]["id"]


def rows_of(db: dict[str, Any], tab_id: int) -> list[dict[str, Any]]:
    """Righe del tab, nell'ordine della dashboard."""
    return [row for row in iter_rows(db) if schema.tab_of(row) == tab_id]


def orphans(db: dict[str, Any]) -> list[dict[str, Any]]:
    """Pannelli di contenuto che nessuna riga possiede."""
    return [panel for _, _, panel, row in iter_panel_slots(db) if row is None]


def panels_of(db: dict[str, Any], tab_id: int) -> list[dict[str, Any]]:
    """Pannelli di contenuto del tab, righe escluse.

    I pannelli fuori riga sono del primo tab: è lì che finiscono anche in
    uscita v2.
    """
    found: list[dict[str, Any]] = []
    for row in rows_of(db, tab_id):
        found.extend(
            child for child in row_children(db, row) if isinstance(child, dict)
        )
    if tab_id == first_id(db):
        found.extend(orphans(db))
    return [panel for panel in found if panel.get("type") != "row"]


def assign(db: dict[str, Any], rows: Iterable[dict[str, Any]], tab_id: int) -> None:
    """Assegna le righe al tab indicato."""
    require(db, tab_id)
    for row in rows:
        row["_tab"] = tab_id


def insert(
    db: dict[str, Any], tab: dict[str, Any], *, position: str = "bottom"
) -> dict[str, Any]:
    """Aggiunge un tab in cima o in fondo."""
    tabs = all_tabs(db)
    if position == "top":
        tabs.insert(0, tab)
    else:
        tabs.append(tab)
    return tab


def move(
    db: dict[str, Any],
    tab_id: int,
    *,
    before: int | None = None,
    after: int | None = None,
    position: str = "bottom",
) -> None:
    """Riordina un tab: prima/dopo un altro, oppure in cima/in fondo."""
    require(db, tab_id)
    if before is not None and before == tab_id:
        raise ValueError("Un tab non si sposta rispetto a se stesso.")
    if after is not None and after == tab_id:
        raise ValueError("Un tab non si sposta rispetto a se stesso.")
    if before is not None:
        require(db, before)
    if after is not None:
        require(db, after)

    tabs = all_tabs(db)
    tab = find(db, tab_id)
    tabs.remove(tab)

    if before is not None:
        tabs.insert(_index(db, before), tab)
    elif after is not None:
        tabs.insert(_index(db, after) + 1, tab)
    elif position == "top":
        tabs.insert(0, tab)
    else:
        tabs.append(tab)


def _index(db: dict[str, Any], tab_id: int) -> int:
    for position, tab in enumerate(all_tabs(db)):
        if tab.get("id") == tab_id:
            return position
    raise ValueError(f"Tab {tab_id} non trovato.")


def remove(
    db: dict[str, Any], tab_id: int, *, keep_rows: bool = False
) -> int:
    """Elimina il tab; ritorna quanti pannelli sono stati eliminati con lui.

    Con `keep_rows` le righe sopravvivono e passano al primo tab rimasto.
    L'ultimo tab non si elimina: la dashboard ne ha sempre almeno uno.
    """
    require(db, tab_id)
    tabs = all_tabs(db)
    if len(tabs) <= 1:
        raise ValueError(
            "L'ultimo tab non si elimina: la dashboard deve averne almeno uno."
        )

    rows = rows_of(db, tab_id)
    removed = 0
    if keep_rows:
        survivors = [tab for tab in tabs if tab.get("id") != tab_id]
        assign(db, rows, survivors[0]["id"])
    else:
        for row in rows:
            removed += remove_row_block(db, row.get("id"))

    tabs[:] = [tab for tab in tabs if tab.get("id") != tab_id]
    return removed
