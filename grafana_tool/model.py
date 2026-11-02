"""Responsabilità unica: navigare la struttura della dashboard.

Fornisce iterator e finder puri sul dizionario della dashboard, senza
modificarlo. Supporta sia lo schema moderno (panels[type=row]) sia quello
legacy (chiave 'rows').
"""
from __future__ import annotations

import re
from typing import Any, Iterator

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
            if key == "rows" or item.get("type") == "row":
                yield item

def iter_all_panels(db: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Itera tutti i pannelli della dashboard, ovunque siano annidati.

    Include righe, pannelli dentro le righe e pannelli top-level non-row.
    Un pannello presente sia in `panels` sia in `rows` viene restituito una
    sola volta.
    """
    roots: list[dict[str, Any]] = []
    for key in ("panels", "rows"):
        v = db.get(key)
        if isinstance(v, list):
            roots.extend(x for x in v if isinstance(x, dict))
    seen: set[int] = set()
    for p in iter_panels(roots):
        if id(p) in seen:
            continue
        seen.add(id(p))
        yield p


def iter_content_panels(db: dict[str, Any]) -> Iterator[dict[str, Any]]:
    """Itera i soli pannelli di contenuto, escludendo i contenitori riga."""
    for p in iter_all_panels(db):
        if p.get("type") != "row":
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


def iter_panels_with_parent(
    db: dict[str, Any],
) -> Iterator[tuple[dict[str, Any] | None, dict[str, Any]]]:
    """Itera `(riga, pannello)` per ogni pannello di contenuto.

    `riga` è il contenitore `type=row` che ospita il pannello, oppure None
    per i pannelli top-level che non appartengono a una riga espansa.
    """
    seen: set[int] = set()
    row_objects = {id(r) for r in iter_rows(db)}

    for row, children in iter_rows_with_children(db):
        for child in children:
            if not isinstance(child, dict):
                continue
            for sub in iter_panels([child]):
                if id(sub) in seen:
                    continue
                seen.add(id(sub))
                yield row, sub

    for key in ("panels", "rows"):
        container = db.get(key)
        if not isinstance(container, list):
            continue
        for p in iter_panels([x for x in container if isinstance(x, dict)]):
            # le righe legacy possono non avere `type`: le riconosciamo per identità
            if p.get("type") == "row" or id(p) in row_objects or id(p) in seen:
                continue
            seen.add(id(p))
            yield None, p


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
            # nella lista `panels` solo i type=row sono righe
            if key == "rows" or item.get("type") == "row":
                return container, i
    return None, -1


def find_row(db: dict[str, Any], row_id: int) -> dict[str, Any] | None:
    """Ritorna la riga con id `row_id`, oppure None."""
    for r in iter_rows(db):
        if r.get("id") == row_id:
            return r
    return None

def find_panel_container(
    db: dict[str, Any], panel_id: int
) -> tuple[list[dict[str, Any]] | None, int]:
    """Ritorna (lista_contenitrice, indice) del pannello, oppure (None, -1).

    La lista contenitrice può essere:
      - `db["panels"]` o `db["rows"]` se il pannello è top-level
      - la `panels` di una riga se il pannello è annidato
    """
    for key in ("panels", "rows"):
        container = db.get(key)
        if not isinstance(container, list):
            continue
        for i, item in enumerate(container):
            if not isinstance(item, dict):
                continue
            if item.get("id") == panel_id:
                return container, i
            nested = item.get("panels")
            if isinstance(nested, list):
                for j, np in enumerate(nested):
                    if isinstance(np, dict) and np.get("id") == panel_id:
                        return nested, j
    return None, -1

def find_panel_parent_row(db: dict[str, Any], panel_id: int) -> dict[str, Any] | None:
    """Ritorna la riga che contiene il pannello, o None se è top-level."""
    for row, children in iter_rows_with_children(db):
        for child in children:
            if not isinstance(child, dict):
                continue
            for sub in iter_panels([child]):
                if sub.get("id") == panel_id:
                    return row
    return None

def get_max_id(db: dict[str, Any]) -> int:
    """Ritorna l'ID massimo presente tra i pannelli (0 se nessuno)."""
    m = 0
    for p in iter_all_panels(db):
        i = p.get("id")
        if isinstance(i, int) and i > m:
            m = i
    return m

def collect_scope(db: dict[str, Any], row_id: int | None) -> list[dict[str, Any]]:
    """Ritorna la lista piatta dei pannelli di contenuto su cui operare.

    Se `row_id` è None restituisce l'intera dashboard; altrimenti solo i
    pannelli della riga indicata. Le righe sono escluse: sono contenitori,
    non pannelli. Solleva ValueError se la riga non esiste.
    """
    if row_id is None:
        return list(iter_content_panels(db))
    row = find_row(db, row_id)
    if row is None:
        raise ValueError(f"Riga {row_id} non trovata.")
    return [
        p for p in iter_panels(row_children(db, row))
        if p.get("type") != "row"
    ]


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
    """
    return re.compile(pattern, re.IGNORECASE)


def find_row_container_by_title(
    db: dict[str, Any], pattern: str
) -> tuple[list[dict[str, Any]] | None, int, dict[str, Any] | None]:
    """Trova (contenitore, indice, riga) per la prima riga il cui titolo matcha `pattern`."""
    rx = title_regex(pattern)
    for key in ("panels", "rows"):
        container = db.get(key)
        if not isinstance(container, list):
            continue
        for i, item in enumerate(container):
            if isinstance(item, dict) and item.get("type") == "row":
                if rx.search(item.get("title") or ""):
                    return container, i, item
    return None, -1, None


def find_row_by_title(db: dict[str, Any], pattern: str) -> dict[str, Any] | None:
    """Trova la prima riga il cui titolo matcha `pattern` (case-insensitive)."""
    _, _, row = find_row_container_by_title(db, pattern)
    return row


def renumber_ids(obj: dict[str, Any], base_id: int) -> int:
    """Assegna ID sequenziali a `obj` e a tutti i pannelli annidati.

    Ritorna il prossimo ID disponibile.
    """
    nid = base_id
    obj["id"] = nid
    nid += 1
    for panel in obj.get("panels") or []:
        panel["id"] = nid
        nid += 1
        for sub in panel.get("panels") or []:
            sub["id"] = nid
            nid += 1
    return nid


def insert_row_after_block(
    db: dict[str, Any], row_id: int, new_row: dict[str, Any]
) -> int:
    """Inserisce `new_row` dopo la riga `row_id` e i suoi pannelli.

    Per una riga espansa il blocco comprende i pannelli top-level che la
    seguono: inserire subito dopo la riga spezzerebbe l'associazione.
    Ritorna l'indice usato per l'inserimento.
    """
    row = find_row(db, row_id)
    container, idx = find_row_container(db, row_id)
    if row is None or container is None:
        raise ValueError(f"Riga {row_id} non trovata.")
    end = idx
    for child in row_children(db, row):
        j = _container_index(container, child)
        if j > end:
            end = j
    container.insert(end + 1, new_row)
    return end + 1


def remove_row_block(db: dict[str, Any], row_id: int) -> int:
    """Rimuove la riga e, se espansa, i pannelli top-level che la seguono.

    Ritorna il numero di pannelli di contenuto rimossi insieme alla riga.
    """
    row = find_row(db, row_id)
    container, idx = find_row_container(db, row_id)
    if row is None or container is None:
        raise ValueError(f"Riga {row_id} non trovata.")
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
        container, idx = find_row_container(db, row.get("id"))
        if container is None:
            raise ValueError(f"Riga {row.get('id')} non trovata.")
        end = idx
        for child in row_children(db, row):
            j = _container_index(container, child)
            if j > end:
                end = j
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
