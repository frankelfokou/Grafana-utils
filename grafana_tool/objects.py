"""objects: righe e pannelli dietro un'unica interfaccia.

I comandi CRUD non sono più uno per tipo di oggetto: `list`, `create`,
`update`, `delete`, `move` ed `extract` ricevono `row` o `panel` come primo
argomento e lavorano su un `Target`, cioè un oggetto con la sua posizione
nella dashboard.

Qui vive tutto ciò che è comune ai due tipi:

  - la selezione (`--id`, `--match-title`, `--match-type`, `--in-row`);
  - i pannelli di contenuto di un oggetto (per una riga, i discendenti);
  - la rimozione, con o senza figli;
  - lo spostamento: una riga tra le righe, un pannello dentro una riga.

Le operazioni che non hanno senso per un tipo vengono rifiutate con un
messaggio esplicito invece di essere ignorate in silenzio.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterable

from grafana_tool.identity import all_titles, unique_title
from grafana_tool.model import (
    append_to_row_block,
    find_panel_container,
    find_row,
    find_row_container,
    insert_row_after_block,
    iter_panel_slots,
    iter_panels,
    iter_rows,
    remove_row_block,
    require_row,
    row_children,
)
from grafana_tool.selection import PanelMatcher

ROW = "row"
PANEL = "panel"
KINDS = (ROW, PANEL)

NOUN = {ROW: "riga", PANEL: "pannello"}
PLURAL = {ROW: "righe", PANEL: "pannelli"}
IN_ROW_HINT = {ROW: "riga", PANEL: "pannello"}


def describe(kind: str, obj: dict[str, Any]) -> str:
    """Etichetta leggibile: `riga 5 'Row B'`."""
    title = obj.get("title") or "(senza titolo)"
    return f"{NOUN[kind]} {obj.get('id', '?')} '{title}'"


@dataclass
class Target:
    """Oggetto selezionato: il tipo, il dizionario e la riga che lo contiene."""

    kind: str
    obj: dict[str, Any]
    parent: dict[str, Any] | None = None

    @property
    def id(self) -> Any:
        return self.obj.get("id")

    @property
    def title(self) -> str:
        value = self.obj.get("title")
        return value if isinstance(value, str) else ""

    @property
    def panel_type(self) -> str:
        value = self.obj.get("type")
        return value if isinstance(value, str) else ""

    def label(self) -> str:
        return describe(self.kind, self.obj)


# ---------------------------------------------------------------- selezione


def iter_targets(db: dict[str, Any], kind: str) -> Iterable[Target]:
    """Tutti gli oggetti del tipo indicato."""
    if kind == ROW:
        for row in iter_rows(db):
            yield Target(ROW, row, None)
        return
    for _, _, panel, row in iter_panel_slots(db):
        yield Target(PANEL, panel, row)


def require_selector(
    kind: str, *, ids: Iterable[int] = (), match_title: str | None = None,
    match_type: str | None = None, in_row: int | None = None,
) -> None:
    """Impedisce operazioni distruttive senza un criterio esplicito."""
    if ids or match_title is not None or match_type is not None or in_row is not None:
        return
    allowed = ["--id", "--match-title"]
    if kind == PANEL:
        allowed += ["--match-type", "--in-row"]
    raise ValueError("Specificare un selettore: " + ", ".join(allowed) + ".")


def _validate_selectors(
    kind: str, match_type: str | None, in_row: int | None
) -> None:
    if match_type is not None and kind != PANEL:
        raise ValueError(
            "--match-type vale solo per i pannelli: le righe sono tutte di tipo row."
        )
    if in_row is not None and kind != PANEL:
        raise ValueError("--in-row vale solo per i pannelli: le righe non si annidano.")


def _missing_ids(db: dict[str, Any], kind: str, missing: list[int]) -> str:
    if kind == PANEL:
        rows = [i for i in missing if find_row(db, i) is not None]
        if rows:
            return f"Id {rows} ∈ riga: usare il tipo `row`."
    if len(missing) == 1:
        article = "Nessuna" if kind == ROW else "Nessun"
        return f"{article} {NOUN[kind]} con id {missing[0]}."
    return f"{PLURAL[kind].capitalize()} non trovate/i: {missing}."


def select_targets(
    db: dict[str, Any],
    kind: str,
    *,
    ids: Iterable[int] = (),
    match_title: str | None = None,
    match_type: str | None = None,
    in_row: int | None = None,
) -> list[Target]:
    """Applica i selettori della CLI agli oggetti del tipo indicato."""
    _validate_selectors(kind, match_type, in_row)
    if in_row is not None:
        require_row(db, in_row)

    wanted = list(dict.fromkeys(int(i) for i in ids))
    wanted_set = set(wanted)
    matcher = PanelMatcher.from_args(match_type, match_title)

    found: list[Target] = []
    for target in iter_targets(db, kind):
        if wanted_set and target.id not in wanted_set:
            continue
        if matcher.any() and not matcher.matches(target.obj):
            continue
        if in_row is not None and (target.parent is None or target.parent.get("id") != in_row):
            continue
        found.append(target)

    missing = [i for i in wanted if i not in {t.id for t in found}]
    if missing:
        raise ValueError(_missing_ids(db, kind, missing))
    return found


def find_target(db: dict[str, Any], kind: str, obj_id: int) -> Target:
    """Un solo oggetto per id, con errore se non esiste."""
    targets = select_targets(db, kind, ids=[obj_id])
    if not targets:
        raise ValueError(_missing_ids(db, kind, [obj_id]))
    return targets[0]


# ------------------------------------------------------------ contenuto


def content_panels(db: dict[str, Any], target: Target) -> list[dict[str, Any]]:
    """Pannelli su cui applicare le operazioni di contenuto.

    Per un pannello è il pannello stesso (con i suoi eventuali annidati);
    per una riga sono tutti i pannelli che le appartengono. Le righe sono
    sempre escluse: sono contenitori, non pannelli.
    """
    if target.kind == ROW:
        roots = [c for c in row_children(db, target.obj) if isinstance(c, dict)]
    else:
        roots = [target.obj]
    return [
        p for p in iter_panels(roots)
        if p.get("type") != "row"
    ]


# --------------------------------------------------------------- scrittura


def set_title(
    db: dict[str, Any], target: Target, title: str, *, dedupe: bool = False
) -> str:
    """Imposta il titolo, eventualmente rendendolo unico nella dashboard."""
    clean = title.strip()
    if not clean:
        raise ValueError("--title non può essere vuoto.")
    if dedupe:
        taken = all_titles(db)
        current = target.obj.get("title")
        if current in taken:
            taken.remove(current)
        clean = unique_title(clean, taken)
    target.obj["title"] = clean
    return clean


def set_collapsed(db: dict[str, Any], target: Target, collapsed: bool) -> None:
    """Cambia lo stato di una riga spostando i figli nella rappresentazione giusta."""
    if target.kind != ROW:
        raise ValueError("--collapsed/--expanded valgono solo per le righe.")
    container, idx = find_row_container(db, target.id)
    if container is None:
        raise ValueError(f"Riga {target.id} non trovata.")
    if container is db.get("rows") and collapsed is False:
        raise ValueError("Le righe dello schema legacy ('rows') non supportano --expanded.")

    row = target.obj
    children = row_children(db, row)
    if collapsed:
        if row.get("collapsed") is False:
            # da espansa a collassata: i fratelli top-level tornano dentro la riga
            row["panels"] = list(children)
            container[:] = [
                item for item in container
                if not any(item is child for child in children)
            ]
    elif row.get("panels"):
        # da collassata a espansa: i figli escono dalla riga, subito dopo
        moving = list(row["panels"])
        row["panels"] = []
        container[idx + 1:idx + 1] = moving
    row["collapsed"] = collapsed


def remove(db: dict[str, Any], target: Target, *, keep_children: bool = False) -> int:
    """Rimuove l'oggetto; ritorna quanti pannelli sono stati eliminati con lui.

    Con `keep_children` i pannelli di una riga vengono promossi a top-level
    invece di essere eliminati.
    """
    if target.kind == PANEL:
        container, idx = find_panel_container(db, target.id)
        if container is None:
            return 0
        del container[idx]
        return 1

    container, idx = find_row_container(db, target.id)
    if container is None:
        return 0
    if not keep_children:
        return remove_row_block(db, target.id)

    children = [c for c in row_children(db, target.obj) if isinstance(c, dict)]
    if container is db.get("rows"):
        del container[idx]
        db.setdefault("panels", []).extend(children)
    elif target.obj.get("panels"):
        container[idx:idx + 1] = children
    else:
        del container[idx]
    return 0


def move_panel(
    db: dict[str, Any], target: Target, row_id: int, *, position: str = "bottom"
) -> None:
    """Sposta un pannello dentro un'altra riga (o all'inizio della stessa)."""
    if target.kind != PANEL:
        raise ValueError("--to-row vale solo per i pannelli.")
    row = require_row(db, row_id)
    if target.parent is not None and target.parent.get("id") == row_id:
        raise ValueError(f"Il pannello {target.id} è già nella riga {row_id}.")

    container, idx = find_panel_container(db, target.id)
    if container is None:
        raise ValueError(f"Pannello {target.id} non trovato.")
    del container[idx]
    insert_in_row(db, row, target.obj, position=position)


def move_panel_relative(
    db: dict[str, Any], target: Target, anchor_id: int, *, after: bool
) -> None:
    """Sposta un pannello prima o dopo un altro pannello dello stesso contenitore."""
    if target.kind != PANEL:
        raise ValueError("--before/--after su un pannello valgono solo per i pannelli.")
    if anchor_id == target.id:
        raise ValueError("Un pannello non si sposta rispetto a se stesso.")

    container, idx = find_panel_container(db, target.id)
    if container is None:
        raise ValueError(f"Pannello {target.id} non trovato.")
    del container[idx]

    anchor_container, anchor_idx = find_panel_container(db, anchor_id)
    if anchor_container is None:
        raise ValueError(f"Pannello {anchor_id} non trovato.")
    anchor_container.insert(anchor_idx + 1 if after else anchor_idx, target.obj)


def insert_in_row(
    db: dict[str, Any], row: dict[str, Any], panel: dict[str, Any], *, position: str = "bottom"
) -> None:
    """Inserisce `panel` nella riga, in testa o in coda al suo blocco."""
    expanded = row.get("collapsed") is False and not (row.get("panels") or [])
    if position == "top":
        if expanded:
            row_container, row_idx = find_row_container(db, row.get("id"))
            if row_container is None:
                raise ValueError(f"Riga {row.get('id')} non trovata.")
            row_container.insert(row_idx + 1, panel)
        else:
            row.setdefault("panels", []).insert(0, panel)
        return
    append_to_row_block(db, row, panel)


def move_row(
    db: dict[str, Any],
    target: Target,
    *,
    before: int | None = None,
    after: int | None = None,
    position: str = "bottom",
) -> None:
    """Riordina una riga: prima/dopo un'altra, oppure in cima/in fondo."""
    if target.kind != ROW:
        raise ValueError("--before/--after/--position tra righe valgono solo per le righe.")
    if before is not None and before == target.id:
        raise ValueError("Una riga non si sposta rispetto a se stessa.")
    if after is not None and after == target.id:
        raise ValueError("Una riga non si sposta rispetto a se stessa.")

    container, idx = find_row_container(db, target.id)
    if container is None:
        raise ValueError(f"Riga {target.id} non trovata.")
    if container is db.get("rows"):
        raise ValueError("Le righe dello schema legacy ('rows') non si riordinano.")
    if before is not None:
        require_row(db, before)
    if after is not None:
        require_row(db, after)

    del container[idx]
    if before is not None:
        anchor_container, anchor_idx = find_row_container(db, before)
        if anchor_container is None:
            raise ValueError(f"Riga {before} non trovata.")
        anchor_container.insert(anchor_idx, target.obj)
    elif after is not None:
        insert_row_after_block(db, after, target.obj)
    elif position == "top":
        container.insert(0, target.obj)
    else:
        container.append(target.obj)
