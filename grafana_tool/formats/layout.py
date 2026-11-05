"""layout: conversione della disposizione.

Nel classico la disposizione vive in due posti:

  - la sequenza di `panels`, dove una riga (`type: "row"`) contiene i figli
    oppure li precede come fratelli se è espansa;
  - `gridPos {x, y, w, h}` su ogni pannello.

Nello schema v2 è un albero esplicito:

    TabsLayout → TabsLayoutTab → RowsLayout → RowsLayoutRow
              → GridLayout → GridLayoutItem (x, y, width, height, element)

Il lettore produce una descrizione piatta e ordinata (`Tree`), lo scrittore
costruisce l'albero a partire dalla dashboard canonica.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from grafana_tool import model, schema

# Dimensioni usate quando un pannello non dichiara gridPos.
DEFAULT_WIDTH = 24
DEFAULT_HEIGHT = 8

ELEMENT_PREFIX = "panel-"


@dataclass(frozen=True)
class Slot:
    """Un pannello collocato: a quale riga appartiene e come è dimensionato."""

    tab_index: int
    row_index: int
    element: str
    grid: dict[str, int]


@dataclass(frozen=True)
class Row:
    """Una riga del layout, anche quando è vuota."""

    tab_index: int
    row_index: int
    title: str
    collapsed: bool


@dataclass
class Tree:
    """Vista piatta del layout v2, nell'ordine in cui appare."""

    tabs: list[str] = field(default_factory=list)
    rows: list[Row] = field(default_factory=list)
    slots: list[Slot] = field(default_factory=list)


# --- lettura ---------------------------------------------------------------


def read_tree(v2: dict[str, Any], report: Any) -> Tree:
    """Trasforma `layout` v2 in una lista ordinata di tab, righe e pannelli."""
    tree = Tree()
    for tab_index, tab in enumerate(
        _tab_nodes(v2.get("layout") or {}, report), start=1
    ):
        tab_spec = tab.get("spec") or {}
        tree.tabs.append(tab_spec.get("title") or "")
        for row_index, row in enumerate(
            _row_nodes(tab_spec.get("layout") or {}, report)
        ):
            row_spec = row.get("spec") or {}
            collapsed = bool(row_spec.get("collapse", False))
            # La riga viene registrata anche senza elementi: lo schema v2 la
            # rappresenta, quindi perderla sarebbe una perdita silenziosa.
            tree.rows.append(
                Row(
                    tab_index=tab_index,
                    row_index=row_index,
                    title=row_spec.get("title") or "",
                    collapsed=collapsed,
                )
            )
            for item in _item_nodes(row_spec.get("layout") or {}, report):
                spec = item.get("spec") or {}
                element = (spec.get("element") or {}).get("name") or ""
                if not element:
                    report.add("partial", "elemento del layout senza nome: ignorato")
                    continue
                tree.slots.append(
                    Slot(
                        tab_index=tab_index,
                        row_index=row_index,
                        element=element,
                        grid={
                            "x": spec.get("x", 0),
                            "y": spec.get("y", 0),
                            "w": spec.get("width", DEFAULT_WIDTH),
                            "h": spec.get("height", DEFAULT_HEIGHT),
                        },
                    )
                )
    return tree


def _tab_nodes(layout: dict[str, Any], report: Any) -> list[dict[str, Any]]:
    """Tab del layout, tollerando un layout che parte dalle righe."""
    kind = layout.get("kind")
    spec = layout.get("spec") or {}
    if kind == "TabsLayout":
        return [t for t in spec.get("tabs") or [] if isinstance(t, dict)]
    if kind == "RowsLayout":
        report.add(
            "lossy",
            "layout senza tab: i contenuti confluiscono in un unico tab",
        )
        return [{"kind": "TabsLayoutTab", "spec": {"title": "", "layout": layout}}]
    if not layout:
        return []
    report.add("partial", f"layout '{kind}' non gestito: nessun contenuto letto")
    return []


def _row_nodes(node: dict[str, Any], report: Any) -> list[dict[str, Any]]:
    """Righe contenute in un nodo di layout."""
    kind = node.get("kind")
    spec = node.get("spec") or {}
    if kind == "RowsLayout":
        return [r for r in spec.get("rows") or [] if isinstance(r, dict)]
    if kind == "RowsLayoutRow":
        return [node]
    if kind == "GridLayout":
        return [{"kind": "RowsLayoutRow", "spec": {"title": "", "layout": node}}]
    if not node:
        return []
    report.add("partial", f"riga con layout '{kind}' non gestito: ignorata")
    return []


def _item_nodes(node: dict[str, Any], report: Any) -> list[dict[str, Any]]:
    """Elementi collocati (`GridLayoutItem`) dentro un nodo di layout."""
    kind = node.get("kind")
    spec = node.get("spec") or {}
    if kind == "GridLayout":
        return [i for i in spec.get("items") or [] if isinstance(i, dict)]
    if kind == "RowsLayout":
        report.add(
            "lossy",
            "righe annidate appiattite nella riga che le contiene",
        )
        out: list[dict[str, Any]] = []
        for row in spec.get("rows") or []:
            if isinstance(row, dict):
                out.extend(_item_nodes((row.get("spec") or {}).get("layout"), report))
        return out
    if not node:
        return []
    report.add("partial", f"layout '{kind}' non gestito: elementi ignorati")
    return []


# --- scrittura -------------------------------------------------------------


def element_names(db: dict[str, Any]) -> dict[int, str]:
    """Nome dell'elemento v2 per ogni pannello, indicizzato per `id()`.

    I pannelli letti da v2 conservano il nome originale in `_element`; quelli
    creati dal tool ricevono `panel-<id>`. I nomi sono resi unici perché in v2
    sono le chiavi della mappa `elements`.
    """
    names: dict[int, str] = {}
    used: set[str] = set()
    for _, _, panel, _ in model.iter_panel_slots(db):
        base = panel.get("_element") or f"{ELEMENT_PREFIX}{panel.get('id', '')}"
        name = base
        suffix = 2
        while name in used:
            name = f"{base}-{suffix}"
            suffix += 1
        used.add(name)
        names[id(panel)] = name
    return names


def write_layout(db: dict[str, Any], names: dict[int, str]) -> dict[str, Any]:
    """Costruisce l'albero `layout` v2 dalla dashboard canonica."""
    tabs = schema.canonical_tabs(db) or [
        {"id": schema.IMPLICIT_TAB_ID, "title": ""}
    ]
    rows = _rows_by_tab(db)
    orphans = _orphan_panels(db)

    tab_nodes: list[dict[str, Any]] = []
    for position, tab in enumerate(tabs):
        row_nodes = [_row_node(db, row, names) for row in rows.get(tab["id"], [])]
        if position == 0 and orphans:
            row_nodes.append(_row_node_from_panels(orphans, names, title=""))
        tab_nodes.append(
            {
                "kind": "TabsLayoutTab",
                "spec": {
                    "title": tab.get("title") or "",
                    "layout": {"kind": "RowsLayout", "spec": {"rows": row_nodes}},
                },
            }
        )
    return {"kind": "TabsLayout", "spec": {"tabs": tab_nodes}}


def _rows_by_tab(db: dict[str, Any]) -> dict[int, list[dict[str, Any]]]:
    """Righe raggruppate per tab, nell'ordine della dashboard.

    Una riga che dichiara un tab inesistente non viene scartata: finisce nel
    primo tab. Perdere una riga perché il suo metadato è sbagliato sarebbe
    il peggior esito possibile di una conversione.
    """
    known = {tab["id"] for tab in schema.canonical_tabs(db)}
    fallback = min(known) if known else schema.IMPLICIT_TAB_ID
    out: dict[int, list[dict[str, Any]]] = {}
    for row in model.iter_rows(db):
        tab_id = schema.tab_of(row)
        if known and tab_id not in known:
            tab_id = fallback
        out.setdefault(tab_id, []).append(row)
    return out


def _orphan_panels(db: dict[str, Any]) -> list[dict[str, Any]]:
    """Pannelli di contenuto che nessuna riga possiede."""
    return [panel for _, _, panel, row in model.iter_panel_slots(db) if row is None]


def _row_node(
    db: dict[str, Any], row: dict[str, Any], names: dict[int, str]
) -> dict[str, Any]:
    """Una riga canonica diventa un `RowsLayoutRow`."""
    return _row_node_from_panels(
        model.row_children(db, row),
        names,
        title=row.get("title") or "",
        collapsed=bool(row.get("collapsed", True)),
    )


def _row_node_from_panels(
    panels: list[dict[str, Any]],
    names: dict[int, str],
    *,
    title: str,
    collapsed: bool = True,
) -> dict[str, Any]:
    """Costruisce un `RowsLayoutRow` dai pannelli che gli appartengono."""
    items = [_grid_item(panel, names) for panel in panels if id(panel) in names]
    return {
        "kind": "RowsLayoutRow",
        "spec": {
            "collapse": collapsed,
            "layout": {"kind": "GridLayout", "spec": {"items": items}},
            "title": title,
        },
    }


def _grid_item(panel: dict[str, Any], names: dict[int, str]) -> dict[str, Any]:
    """Un pannello diventa un `GridLayoutItem`."""
    grid = panel.get("gridPos") or {}
    return {
        "kind": "GridLayoutItem",
        "spec": {
            "element": {"kind": "ElementReference", "name": names[id(panel)]},
            "x": grid.get("x", 0),
            "y": grid.get("y", 0),
            "width": grid.get("w", DEFAULT_WIDTH),
            "height": grid.get("h", DEFAULT_HEIGHT),
        },
    }
