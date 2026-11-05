"""flatten: trasformare più tab nell'unica vista del formato classico.

Il JSON model classico non ha tab: ha una sequenza di righe e pannelli. Quando
la dashboard di partenza ne ha più di uno, la conversione non si ferma e non
sceglie per l'utente: li appiattisce in una sola vista, nell'ordine in cui i
tab compaiono.

Due cose rendono la vista leggibile:

  - **prefisso**: il titolo di ogni oggetto di primo livello (righe e pannelli
    fuori riga) riceve il nome del tab di provenienza, `<tab>-<titolo>`. Senza
    prefisso due righe "Generale" di tab diversi sarebbero indistinguibili;
  - **impilamento**: in v2 ogni riga ha un proprio spazio di coordinate che
    parte da `y = 0`. Nel classico lo spazio è unico, quindi le righe vengono
    riposizionate in colonna: intestazione a `y`, figli da `y + 1`.

L'impilamento serve anche a una dashboard a un solo tab letta da v2: le sue
righe sarebbero altrimenti tutte a `y = 0`. Per questo il lettore marca le
righe con `_relative_grid` e qui si riposiziona solo quando quel marcatore
c'è: una dashboard già classica non viene toccata.

Il modulo lavora su una copia: il modello canonico della dashboard resta con i
suoi tab.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from grafana_tool import model, schema

# Griglia usata per un pannello che non ne dichiara una.
DEFAULT_GRID = {"x": 0, "y": 0, "w": 12, "h": 8}

# Griglia dell'intestazione di riga, come la scrive Grafana.
ROW_GRID = {"h": 1, "w": 24, "x": 0, "y": 0}


@dataclass(frozen=True)
class Rename:
    """Titolo di primo livello cambiato dall'appiattimento."""

    kind: str      # "row" | "panel"
    before: str
    after: str


@dataclass
class Result:
    """Esito dell'appiattimento."""

    renames: list[Rename] = field(default_factory=list)
    moved_orphans: int = 0
    restacked: bool = False


@dataclass
class _Block:
    """Gruppo indivisibile della vista: una riga con i suoi pannelli."""

    tab_id: int | None
    row: dict[str, Any] | None
    children: list[dict[str, Any]]
    expanded: bool


def prefixed(prefix: str, title: Any) -> str:
    """`<tab>-<titolo>`; con titolo vuoto resta il solo nome del tab."""
    clean = (title or "").strip() if isinstance(title, str) else ""
    label = (prefix or "").strip()
    if not label:
        return clean
    return f"{label}-{clean}" if clean else label


def flatten(db: dict[str, Any]) -> Result:
    """Appiattisce i tab di `db` e ne impila le righe (`db` viene modificato)."""
    tabs = schema.canonical_tabs(db)
    result = Result()

    if len(tabs) > 1:
        result.renames, result.moved_orphans = _merge_tabs(db, tabs)

    if len(tabs) > 1 or needs_restack(db):
        _restack_dashboard(db)
        result.restacked = True
    return result


def needs_restack(db: dict[str, Any]) -> bool:
    """Vero se le righe portano coordinate relative a se stesse (origine v2)."""
    return any(row.get("_relative_grid") for row in model.iter_rows(db))


def _merge_tabs(
    db: dict[str, Any], tabs: list[dict[str, Any]]
) -> tuple[list[Rename], int]:
    """Unisce i tab in uno solo, prefissando i titoli di primo livello."""
    titles = {tab["id"]: (tab.get("title") or "") for tab in tabs}
    first = tabs[0]["id"]

    blocks = _blocks(db)
    ordered = [
        block for tab in tabs
        for block in blocks
        if block.row is not None and block.tab_id == tab["id"]
    ]
    orphans = [block for block in blocks if block.row is None]
    ordered.extend(orphans)

    renames: list[Rename] = []
    for block in ordered:
        if block.row is not None:
            rename = _apply(block.row, titles.get(block.tab_id, ""), "row")
            if rename:
                renames.append(rename)
            block.row["_tab"] = first
        else:
            for panel in block.children:
                rename = _apply(panel, titles.get(first, ""), "panel")
                if rename:
                    renames.append(rename)

    db["panels"] = _entries(ordered)
    db["_tabs"] = [{"id": first, "title": ""}]
    return renames, sum(len(block.children) for block in orphans)


def _apply(obj: dict[str, Any], prefix: str, kind: str) -> Rename | None:
    """Prefissa il titolo di `obj`, se il prefisso esiste."""
    if not (prefix or "").strip():
        return None
    before = obj.get("title") or ""
    after = prefixed(prefix, before)
    if after == before:
        return None
    obj["title"] = after
    return Rename(kind=kind, before=before, after=after)


def _blocks(db: dict[str, Any]) -> list[_Block]:
    """Raggruppa le righe con i figli, lasciando fuori riga i pannelli liberi."""
    owned: set[int] = set()
    for row in model.iter_rows(db):
        for child in model.row_children(db, row):
            owned.add(id(child))

    blocks: list[_Block] = []
    for item in db.get("panels") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "row":
            children = [c for c in model.row_children(db, item) if isinstance(c, dict)]
            expanded = item.get("collapsed") is False and not item.get("panels")
            blocks.append(_Block(schema.tab_of(item), item, children, expanded))
        elif id(item) in owned:
            continue
        else:
            blocks.append(_Block(None, None, [item], False))
    return blocks


def _grid(panel: dict[str, Any]) -> dict[str, int]:
    """Griglia del pannello, sintetizzata se manca."""
    raw = panel.get("gridPos")
    grid = dict(DEFAULT_GRID)
    if isinstance(raw, dict):
        for key, default in DEFAULT_GRID.items():
            value = raw.get(key, default)
            grid[key] = int(value) if isinstance(value, (int, float)) else default
    panel["gridPos"] = grid
    return grid


def _restack_dashboard(db: dict[str, Any]) -> None:
    """Impila i blocchi in colonna a partire da `y = 0`."""
    blocks = _blocks(db)
    cursor = 0
    for block in blocks:
        if block.row is not None:
            block.row["gridPos"] = dict(ROW_GRID, y=cursor)
            cursor += 1
        if block.children:
            cursor = _place(block.children, cursor)
    db["panels"] = _entries(blocks)


def _place(children: list[dict[str, Any]], top: int) -> int:
    """Porta i figli a partire da `top`, conservando le posizioni relative."""
    grids = [_grid(panel) for panel in children]
    base = min(grid["y"] for grid in grids)
    for grid in grids:
        grid["y"] = top + (grid["y"] - base)
    return max(grid["y"] + grid["h"] for grid in grids)


def _entries(blocks: list[_Block]) -> list[dict[str, Any]]:
    """Lista `panels` piatta, con le righe espanse seguite dai loro pannelli."""
    out: list[dict[str, Any]] = []
    for block in blocks:
        if block.row is None:
            out.extend(block.children)
            continue
        out.append(block.row)
        if block.expanded:
            out.extend(block.children)
    return out
