"""Responsabilità unica: navigare la struttura della dashboard.

Fornisce iterator e finder puri sul dizionario della dashboard, senza
modificarlo. Supporta sia lo schema moderno (panels[type=row]) sia quello
legacy (chiave 'rows').
"""
from __future__ import annotations

import re
from typing import Any, Iterator

def _is_row(key: str, item: dict[str, Any]) -> bool:
    """Vero se `item` è una riga.

    Nella lista legacy `rows` ogni elemento è una riga; nella lista `panels`
    lo è solo chi ha `type: "row"`. Regola unica per tutti gli attraversamenti.
    """
    return key == "rows" or item.get("type") == "row"


def dashboard_roots(db: dict[str, Any]) -> list[dict[str, Any]]:
    """Elementi top-level delle liste `panels` e `rows`, senza duplicati."""
    roots: list[dict[str, Any]] = []
    seen: set[int] = set()
    for key in ("panels", "rows"):
        container = db.get(key)
        if not isinstance(container, list):
            continue
        for item in container:
            if isinstance(item, dict) and id(item) not in seen:
                seen.add(id(item))
                roots.append(item)
    return roots


def iter_panels(panels: list[dict[str, Any]]) -> Iterator[dict[str, Any]]:
    """Itera ricorsivamente tutti i pannelli, inclusi quelli annidati."""
    for p in panels:
        if not isinstance(p, dict):
            continue
        yield p
        nested = p.get("panels")
        if isinstance(nested, list):
            yield from iter_panels(nested)

def iter_rows(db: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Itera tutte le righe, unendo schema moderno e legacy senza duplicati."""
    seen: set[int] = set()
    for key in ("panels", "rows"):
        container = db.get(key)
        if not isinstance(container, list):
            continue
        for item in container:
            if not isinstance(item, dict) or id(item) in seen:
                continue
            seen.add(id(item))
            if _is_row(key, item):
                yield item

def iter_all_panels(db: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Itera tutti i pannelli della dashboard, ovunque siano annidati.

    Include righe, pannelli dentro le righe e pannelli top-level non-row.
    Un pannello presente sia in `panels` sia in `rows` viene restituito una
    sola volta.
    """
    seen: set[int] = set()
    for p in iter_panels(dashboard_roots(db)):
        if id(p) in seen:
            continue
        seen.add(id(p))
        yield p


def _container_index(container: list[Any], target: Any) -> int:
    """Indice di `target` nella lista, confrontato per identità (-1 se assente)."""
    for i, item in enumerate(container):
        if item is target:
            return i
    return -1


def expanded_row_siblings(
    db: dict[str, Any], row: dict[str, Any]
) -> list[dict[str, Any]]:
    """Pannelli top-level che seguono una riga espansa fino alla riga successiva.

    Grafana salva le righe espanse (`collapsed: false`) senza figli dentro
    `row["panels"]`: i pannelli restano top-level e vengono associati alla
    riga solo dalla posizione nella lista `panels`.
    """
    container = db.get("panels")
    if not isinstance(container, list):
        return []
    idx = _container_index(container, row)
    if idx < 0:
        return []
    out: list[dict[str, Any]] = []
    for item in container[idx + 1:]:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "row":
            break
        out.append(item)
    return out


def row_children(
    db: dict[str, Any], row: dict[str, Any]
) -> list[dict[str, Any]]:
    """Pannelli che appartengono alla riga, in entrambe le rappresentazioni.

    - riga collassata o schema legacy: i pannelli annidati in `row["panels"]`;
    - riga espansa (`collapsed: false`) senza figli annidati: i pannelli
      top-level che la seguono, come fa Grafana.
    """
    if not isinstance(row, dict):
        return []
    explicit = row.get("panels")
    if isinstance(explicit, list) and explicit:
        return list(explicit)
    if row.get("collapsed") is False:
        return expanded_row_siblings(db, row)
    return []


def iter_rows_with_children(
    db: dict[str, Any],
) -> Iterator[tuple[dict[str, Any], list[dict[str, Any]]]]:
    """Itera `(riga, pannelli)` applicando la semantica delle righe espanse."""
    for row in iter_rows(db):
        yield row, row_children(db, row)


def iter_panel_slots(
    db: dict[str, Any],
) -> Iterator[
    tuple[list[dict[str, Any]], int, dict[str, Any], dict[str, Any] | None]
]:
    """Itera `(contenitore, indice, pannello, riga)` per ogni pannello di contenuto.

    `riga` è la riga che possiede il pannello: quella che lo contiene, oppure
    la riga espansa di cui il pannello è fratello top-level. Le righe non
    vengono restituite. È l'attraversamento unico usato da `objects.py` per
    selezionare, elencare, spostare e rimuovere i pannelli.
    """
    owners: dict[int, dict[str, Any]] = {}
    for row, children in iter_rows_with_children(db):
        for child in children:
            if isinstance(child, dict):
                owners[id(child)] = row

    seen: set[int] = set()

    def walk(
        container: list[dict[str, Any]], row: dict[str, Any] | None
    ) -> Iterator[
        tuple[list[dict[str, Any]], int, dict[str, Any], dict[str, Any] | None]
    ]:
        for i, item in enumerate(container):
            if not isinstance(item, dict) or id(item) in seen:
                continue
            if item.get("type") == "row":
                nested = item.get("panels")
                if isinstance(nested, list):
                    yield from walk(nested, item)
                continue
            seen.add(id(item))
            yield container, i, item, owners.get(id(item), row)
            nested = item.get("panels")
            if isinstance(nested, list):
                yield from walk(nested, row)

    top = db.get("panels")
    if isinstance(top, list):
        yield from walk(top, None)
    # Lo schema legacy tiene le righe e i loro figli fuori da `panels`.
    for row in iter_rows(db):
        nested = row.get("panels")
        if isinstance(nested, list):
            yield from walk(nested, row)


def find_row_container(
    db: dict[str, Any], row_id: int
) -> tuple[list[dict[str, Any]] | None, int]:
    """Ritorna (lista_contenitrice, indice) della riga, oppure (None, -1)."""
    for key in ("panels", "rows"):
        container = db.get(key)
        if not isinstance(container, list):
            continue
        for i, item in enumerate(container):
            if not isinstance(item, dict) or item.get("id") != row_id:
                continue
            if _is_row(key, item):
                return container, i
    return None, -1


def find_row(db: dict[str, Any], row_id: int) -> dict[str, Any] | None:
    """Ritorna la riga con id `row_id`, oppure None."""
    for r in iter_rows(db):
        if r.get("id") == row_id:
            return r
    return None


def require_row(db: dict[str, Any], row_id: int, *, where: str = "") -> dict[str, Any]:
    """Come `find_row`, ma solleva `ValueError` se la riga non esiste."""
    row = find_row(db, row_id)
    if row is None:
        raise ValueError(f"Riga {row_id} non trovata{where}.")
    return row

def find_panel_container(
    db: dict[str, Any], panel_id: int
) -> tuple[list[dict[str, Any]] | None, int]:
    """Ritorna (lista_contenitrice, indice) del pannello, oppure (None, -1).

    La lista contenitrice può essere `db["panels"]`, `db["rows"]`, le
    `panels` di una riga o di un pannello annidato.
    """
    for container, idx, panel, _ in iter_panel_slots(db):
        if panel.get("id") == panel_id:
            return container, idx
    return None, -1


def get_max_id(db: dict[str, Any]) -> int:
    """Ritorna l'ID massimo presente tra i pannelli (0 se nessuno)."""
    m = 0
    for p in iter_all_panels(db):
        i = p.get("id")
        if isinstance(i, int) and i > m:
            m = i
    return m


def max_y(db: dict[str, Any]) -> int:
    """Ritorna il massimo gridPos.y + gridPos.h tra tutti i pannelli (inclusi annidati)."""
    m = 0
    for p in iter_all_panels(db):
        gp = p.get("gridPos") or {}
        y = gp.get("y", 0) or 0
        h = gp.get("h", 0) or 0
        m = max(m, int(y) + int(h))
    return m


def title_regex(pattern: str) -> "re.Pattern[str]":
    """Compila una regex per i titoli, sempre case-insensitive.

    In Grafana un titolo è un'etichetta: l'identificazione per nome non deve
    dipendere da maiuscole/minuscole. Tutti i comandi che cercano per titolo
    passano da qui.

    Una regex scritta male diventa un `ValueError` con il messaggio di Python:
    senza questa conversione la CLI uscirebbe con un traceback invece che con
    un errore leggibile e il relativo log.
    """
    try:
        return re.compile(pattern, re.IGNORECASE)
    except re.error as exc:
        raise ValueError(f"espressione regolare non valida {pattern!r}: {exc}") from exc


def renumber_ids(obj: dict[str, Any], base_id: int) -> int:
    """Assegna ID sequenziali a `obj` e a tutti i pannelli annidati.

    Ritorna il prossimo ID disponibile. Usa `iter_panels`, quindi funziona a
    qualsiasi profondità.
    """
    nid = base_id
    for panel in iter_panels([obj]):
        panel["id"] = nid
        nid += 1
    return nid


def _block_end(
    container: list[dict[str, Any]], idx: int, children: list[dict[str, Any]]
) -> int:
    """Ultimo indice occupato nella lista dal blocco riga (riga + figli)."""
    end = idx
    for child in children:
        j = _container_index(container, child)
        if j > end:
            end = j
    return end


def row_block(
    db: dict[str, Any], row_id: int
) -> tuple[list[dict[str, Any]], int, dict[str, Any]]:
    """Ritorna `(contenitore, indice, riga)` del blocco riga.

    Solleva `ValueError` se la riga non esiste: unico punto in cui i comandi
    che manipolano un blocco riga gestiscono quel caso.
    """
    container, idx = find_row_container(db, row_id)
    if container is None:
        raise ValueError(f"Riga {row_id} non trovata.")
    return container, idx, require_row(db, row_id)


def insert_row_after_block(
    db: dict[str, Any], row_id: int, new_row: dict[str, Any]
) -> int:
    """Inserisce `new_row` dopo la riga `row_id` e i suoi pannelli.

    Per una riga espansa il blocco comprende i pannelli top-level che la
    seguono: inserire subito dopo la riga spezzerebbe l'associazione.
    Ritorna l'indice usato per l'inserimento.
    """
    container, idx, row = row_block(db, row_id)
    end = _block_end(container, idx, row_children(db, row))
    container.insert(end + 1, new_row)
    return end + 1


def remove_row_block(db: dict[str, Any], row_id: int) -> int:
    """Rimuove la riga e, se espansa, i pannelli top-level che la seguono.

    Ritorna il numero di pannelli di contenuto rimossi insieme alla riga.
    """
    container, idx, row = row_block(db, row_id)
    children = row_children(db, row)
    positions = {idx}
    for child in children:
        j = _container_index(container, child)
        if j >= 0:
            positions.add(j)
    for j in sorted(positions, reverse=True):
        container.pop(j)
    return len(children)


def append_to_row_block(
    db: dict[str, Any], row: dict[str, Any], panel: dict[str, Any]
) -> None:
    """Aggiunge `panel` alla riga rispettandone la rappresentazione.

    Riga espansa: il pannello va top-level in coda al blocco della riga.
    Riga collassata o legacy: il pannello va dentro `row["panels"]`.
    """
    if row.get("collapsed") is False and not (row.get("panels") or []):
        container, idx, _ = row_block(db, row.get("id"))
        end = _block_end(container, idx, row_children(db, row))
        container.insert(end + 1, panel)
        return
    row.setdefault("panels", []).append(panel)


def min_grid_y(db_or_panels: Any) -> int:
    """Minimo `gridPos.y` tra i pannelli indicati (0 se non ce ne sono)."""
    if isinstance(db_or_panels, dict):
        panels: list[dict[str, Any]] = list(iter_all_panels(db_or_panels))
    else:
        panels = list(iter_panels(list(db_or_panels or [])))
    ys = []
    for p in panels:
        gp = p.get("gridPos")
        if isinstance(gp, dict):
            ys.append(int(gp.get("y", 0) or 0))
    return min(ys) if ys else 0


def shift_grid_y(panels: list[dict[str, Any]], delta: int) -> None:
    """Somma `delta` a `gridPos.y` di ogni pannello (annidati compresi)."""
    if not delta:
        return
    for p in iter_panels([x for x in panels or [] if isinstance(x, dict)]):
        gp = p.get("gridPos")
        if isinstance(gp, dict):
            gp["y"] = int(gp.get("y", 0) or 0) + delta


def shift_dashboard_grid_y(db: dict[str, Any], delta: int) -> None:
    """Somma `delta` a `gridPos.y` di tutta la dashboard, senza doppi conteggi."""
    shift_grid_y(dashboard_roots(db), delta)


def stack_grid_y(panels: list[dict[str, Any]], start_y: int) -> int:
    """Dispone i pannelli in colonna da `start_y`; ritorna l'altezza usata."""
    y = start_y
    for child in panels or []:
        gp = child.get("gridPos") if isinstance(child.get("gridPos"), dict) else {}
        gp["y"] = y
        child["gridPos"] = gp
        y += int(gp.get("h", 4) or 4)
    return max(1, y - start_y)
