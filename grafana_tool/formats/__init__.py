"""formats: conversione tra JSON model classico e schema v2.

Un solo punto di ingresso (`load`) e uno di uscita (`render`). Nessun comando
conosce il formato del file: riceve sempre il **modello canonico**, che è il
JSON model classico esteso con i tab.

    file classico ─┐
                   ├─ load ─→ canonico ─→ comando ─→ render ─→ file
    file v2 ───────┘

Le conversioni sono affidate a un adattatore per elemento
(`dashboard`, `variables`, `panel`, `queries`, `layout`), ognuno puro: dizionari
in ingresso, dizionari in uscita, nessun I/O e nessun `argparse`.

Ogni adattatore dichiara la propria fedeltà. Quando una conversione perde
qualcosa lo scrive in un `Report`, che il comando stampa: una perdita tacita
sarebbe un dato cancellato senza avviso.
"""
from __future__ import annotations

import copy
from collections import Counter
from dataclasses import dataclass, field
from typing import Any

from grafana_tool import model, schema
from grafana_tool.io import InputError

from . import dashboard, flatten as flatten_module, layout, panel, queries, variables

__all__ = [
    "Report",
    "Loaded",
    "load",
    "read_v2",
    "render",
    "EXACT",
    "LOSSY",
    "PARTIAL",
    "INFO",
    "dashboard",
    "flatten",
    "layout",
    "panel",
    "queries",
    "variables",
]

# Gradi di fedeltà di una conversione.
EXACT = "exact"
LOSSY = "lossy"
PARTIAL = "partial"
INFO = "info"

FIDELITY_LABEL = {
    EXACT: "esatta",
    LOSSY: "con perdita",
    PARTIAL: "parziale",
    INFO: "nota",
}


@dataclass
class Report:
    """Perdite e anomalie incontrate durante una conversione."""

    entries: list[tuple[str, str]] = field(default_factory=list)

    def add(self, fidelity: str, message: str) -> None:
        """Registra una perdita dichiarata (una sola volta)."""
        entry = (fidelity, message)
        if entry not in self.entries:
            self.entries.append(entry)

    def __bool__(self) -> bool:
        return bool(self.entries)

    def __len__(self) -> int:
        return len(self.entries)

    def lines(self) -> list[str]:
        """Righe da stampare, raggruppate per grado di fedeltà."""
        if not self.entries:
            return []
        out = ["Conversione del formato:"]
        for fidelity, message in self.entries:
            out.append(f"  [{FIDELITY_LABEL.get(fidelity, fidelity)}] {message}")
        return out

    def as_dicts(self) -> list[dict[str, str]]:
        """Rappresentazione serializzabile (per `--format json`)."""
        return [
            {"fidelity": fidelity, "message": message}
            for fidelity, message in self.entries
        ]


@dataclass
class Loaded:
    """Dashboard canonica pronta per un comando, con la sua provenienza."""

    db: dict[str, Any]
    report: Report
    source: str

    @property
    def target_default(self) -> str:
        """Formato di uscita quando `--to-format` non è specificato."""
        return self.source


# --- ingresso --------------------------------------------------------------


def load(raw: dict[str, Any], *, command: str = "") -> Loaded:
    """Riconosce il formato e restituisce la dashboard canonica.

    Solleva `InputError` se il formato non è riconoscibile: senza questo
    controllo un file v2 verrebbe attraversato come classico, producendo zero
    pannelli e una validazione verde su un file mai letto.
    """
    source = schema.require_recognized(raw, command=command)
    if source == schema.V2:
        db, report = read_v2(raw)
        return Loaded(db, report, source)
    schema.ensure_tabs(raw)
    return Loaded(raw, Report(), source)


def read_v2(v2: dict[str, Any]) -> tuple[dict[str, Any], Report]:
    """Converte una dashboard v2 nel modello canonico."""
    report = Report()
    db: dict[str, Any] = {}
    dashboard.read_into(v2, db, report)
    variables.read_into(v2, db, report)

    tree = layout.read_tree(v2, report)
    titles = tree.tabs or [""]
    db["_tabs"] = [{"id": i, "title": title} for i, title in enumerate(titles, 1)]
    db["panels"] = _build_panels(v2, tree, report)
    _assign_missing_ids(db)
    return db, report


def _build_panels(
    v2: dict[str, Any], tree: layout.Tree, report: Report
) -> list[dict[str, Any]]:
    """Ricostruisce la lista `panels` classica a partire da `layout`."""
    elements = v2.get("elements") or {}

    counts = Counter(slot.element for slot in tree.slots)
    shared = sorted(name for name, count in counts.items() if count > 1)
    if shared:
        raise InputError(
            "elementi collocati in più posizioni del layout: "
            f"{', '.join(shared)}. Il JSON model classico non ha riferimenti "
            "multipli allo stesso pannello."
        )
    for name in sorted(set(elements) - set(counts)):
        report.add(
            LOSSY, f"elemento '{name}' non è collocato nel layout: ignorato"
        )

    by_row: dict[tuple[int, int], list[layout.Slot]] = {}
    for slot in tree.slots:
        by_row.setdefault((slot.tab_index, slot.row_index), []).append(slot)

    root: list[dict[str, Any]] = []
    for row_spec in tree.rows:
        row = {
            "type": "row",
            "title": row_spec.title,
            "collapsed": row_spec.collapsed,
            "panels": [],
            "_tab": row_spec.tab_index,
            # In v2 ogni riga ha una griglia propria che parte da y = 0: le
            # posizioni dei figli sono relative alla riga, non alla dashboard.
            "_relative_grid": True,
        }
        root.append(row)
        # Una riga espansa tiene i figli come fratelli top-level, come fa
        # Grafana: è la rappresentazione che il classico si aspetta.
        target = row["panels"] if row_spec.collapsed else root

        for slot in by_row.get((row_spec.tab_index, row_spec.row_index), []):
            element = elements.get(slot.element)
            if not isinstance(element, dict):
                report.add(
                    PARTIAL,
                    f"'{slot.element}' non esiste in 'elements': posizione ignorata",
                )
                continue
            child = panel.read_panel(slot.element, element, report)
            child["gridPos"] = dict(slot.grid)
            child["_element"] = slot.element
            target.append(child)

    return root


def _assign_missing_ids(db: dict[str, Any]) -> None:
    """Assegna un id a chi non ne dichiara uno."""
    next_id = model.get_max_id(db)
    for obj in model.iter_all_panels(db):
        if not isinstance(obj.get("id"), int):
            next_id += 1
            obj["id"] = next_id


# --- uscita ----------------------------------------------------------------


def render(
    db: dict[str, Any],
    target: str,
    *,
    drop_alerts: bool = False,
    keep_variable_visibility: bool = False,
    keep_literal_values: bool = False,
) -> tuple[dict[str, Any], Report]:
    """Converte il modello canonico nel formato richiesto.

    `target` vale `schema.CLASSIC` o `schema.V2`; per il classico il risultato
    è la dashboard canonica senza le chiavi di servizio.

    Prima della conversione il documento di uscita viene normalizzato sulle
    variabili: tutte visibili in alto e, nei pannelli, valori fissi sostituiti
    dal riferimento alla variabile (`cluster_gen="3"` → `cluster_gen="$cluster_gen"`).
    Le due regole si spengono con `keep_variable_visibility` e
    `keep_literal_values`.
    """
    out = copy.deepcopy(db)
    report = Report()
    variables.normalize(
        out,
        report,
        show_all=not keep_variable_visibility,
        substitute=not keep_literal_values,
    )
    if target == schema.V2:
        return _render_v2(out, drop_alerts=drop_alerts, report=report)
    return _render_classic(out, report=report)


def _render_classic(db: dict[str, Any], *, report: Report) -> tuple[dict[str, Any], Report]:
    """Uscita classica: un solo tab, titoli prefissati e righe impilate."""
    out = db

    result = flatten_module.flatten(out)
    if result.renames:
        report.add(
            LOSSY,
            f"{len(result.renames)} oggetti di primo livello hanno ricevuto il "
            "prefisso del tab di provenienza (<tab>-<titolo>)",
        )
    if result.moved_orphans:
        report.add(
            LOSSY,
            f"{result.moved_orphans} pannelli fuori riga spostati in fondo alla "
            "vista unica",
        )
    if result.restacked:
        report.add(
            INFO,
            "righe impilate in colonna: lo schema v2 dà a ogni riga coordinate "
            "proprie, il classico ne ha una sola",
        )

    missing = [key for key in dashboard.V2_ABSENT_KEYS if key not in out]
    if missing:
        # Tipico di una dashboard letta da v2 e riscritta in classico: lo
        # schema v2 non ha identità, quindi il file ne è privo. Grafana la
        # assegna all'import, ma l'utente deve saperlo.
        report.add(
            INFO,
            "dashboard senza " + ", ".join(missing)
            + ": l'identità sarà assegnata da Grafana all'import",
        )

    schema.strip_internal(out)
    return out, report


def _render_v2(
    db: dict[str, Any], *, drop_alerts: bool, report: Report
) -> tuple[dict[str, Any], Report]:
    """Uscita v2: `elements` + `layout` ricostruiti dal canonico."""
    _guard_alerts(db, drop_alerts)
    _report_stray_rows(db, report)

    out: dict[str, Any] = {}
    dashboard.write_into(db, out, report)
    variables.write_into(db, out, report)

    names = layout.element_names(db)
    out["layout"] = layout.write_layout(db, names)
    out["elements"] = {
        names[id(content)]: panel.write_panel(content)
        for _, _, content, _ in model.iter_panel_slots(db)
        if id(content) in names
    }
    return out, report


def _report_stray_rows(db: dict[str, Any], report: Report) -> None:
    """Dichiara le righe il cui tab non esiste più.

    `layout` le rimette nel primo tab invece di scartarle; qui lo si dice,
    perché un metadato incoerente è un difetto da vedere, non da nascondere.
    """
    known = {tab["id"] for tab in schema.canonical_tabs(db)}
    if not known:
        return
    for row in model.iter_rows(db):
        if schema.tab_of(row) in known:
            continue
        report.add(
            LOSSY,
            f"riga '{row.get('title') or row.get('id')}' con tab "
            f"{schema.tab_of(row)} inesistente: assegnata al primo tab",
        )


def _guard_alerts(db: dict[str, Any], drop_alerts: bool) -> None:
    """Rifiuta di perdere le regole di alert senza un consenso esplicito."""
    if drop_alerts:
        return
    alerted = [
        content
        for _, _, content, _ in model.iter_panel_slots(db)
        if content.get("alert") or content.get("alertId")
    ]
    if not alerted:
        return
    names = ", ".join(
        str(content.get("title") or content.get("id")) for content in alerted
    )
    raise InputError(
        f"{len(alerted)} pannelli hanno regole di alert legacy ({names}), che lo "
        "schema v2 non rappresenta. Usa --drop-alerts per rimuoverle "
        "consapevolmente."
    )
