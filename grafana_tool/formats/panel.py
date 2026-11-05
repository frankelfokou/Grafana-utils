"""panel: conversione del corpo di un pannello.

Nel classico il tipo del pannello è `type` e la configurazione sta in
`fieldConfig` + `options`. Nello schema v2 il tipo è `vizConfig.group` e la
configurazione sta in `vizConfig.spec.fieldConfig` + `vizConfig.spec.options`.

Tutto il resto (titolo, descrizione, trasparenza, link, libreria) è
pass-through esatto.
"""
from __future__ import annotations

import copy
from typing import Any

from grafana_tool.formats import queries

# Versione dello schema di visualizzazione prodotta in uscita.
VIZ_CONFIG_VERSION = "13.0.1"

# Tipo assegnato a un pannello che non ne dichiara uno.
DEFAULT_VIZ_GROUP = "timeseries"


def read_panel(name: str, element: dict[str, Any], report: Any) -> dict[str, Any]:
    """Converte un elemento v2 nel pannello canonico (senza `gridPos`)."""
    kind = element.get("kind")
    if kind != "Panel":
        report.add(
            "partial",
            f"elemento '{name}': kind '{kind}' non è un pannello, letto come tale",
        )
    spec = element.get("spec") or {}
    viz = spec.get("vizConfig") or {}
    viz_spec = viz.get("spec") or {}

    panel: dict[str, Any] = {
        "title": spec.get("title") or "",
        "description": spec.get("description") or "",
        "type": viz.get("group") or DEFAULT_VIZ_GROUP,
        "fieldConfig": copy.deepcopy(viz_spec.get("fieldConfig") or {}),
        "options": copy.deepcopy(viz_spec.get("options") or {}),
    }
    if isinstance(spec.get("id"), int):
        panel["id"] = spec["id"]
    if spec.get("transparent"):
        panel["transparent"] = True
    if spec.get("links"):
        panel["links"] = copy.deepcopy(spec["links"])
    if spec.get("libraryPanel"):
        panel["libraryPanel"] = copy.deepcopy(spec["libraryPanel"])

    targets, extra = queries.read_targets(spec, report)
    panel["targets"] = targets
    panel.update(extra)
    return panel


def write_panel(panel: dict[str, Any]) -> dict[str, Any]:
    """Converte un pannello canonico in un elemento v2 `Panel`."""
    viz_spec: dict[str, Any] = {
        "fieldConfig": copy.deepcopy(
            panel.get("fieldConfig") or {"defaults": {}, "overrides": []}
        ),
        "options": copy.deepcopy(panel.get("options") or {}),
    }
    data_spec: dict[str, Any] = {
        "queries": queries.write_targets(panel),
        "queryOptions": copy.deepcopy(panel.get("queryOptions") or {}),
        "transformations": queries.write_transformations(
            panel.get("transformations") or []
        ),
    }
    spec: dict[str, Any] = {
        "data": {"kind": "QueryGroup", "spec": data_spec},
        "description": panel.get("description") or "",
        "id": panel.get("id"),
        "links": copy.deepcopy(panel.get("links") or []),
        "title": panel.get("title") or "",
        "vizConfig": {
            "group": panel.get("type") or DEFAULT_VIZ_GROUP,
            "kind": "VizConfig",
            "spec": viz_spec,
            "version": VIZ_CONFIG_VERSION,
        },
    }
    if panel.get("transparent"):
        spec["transparent"] = True
    if panel.get("libraryPanel"):
        spec["libraryPanel"] = copy.deepcopy(panel["libraryPanel"])
    return {"kind": "Panel", "spec": spec}
