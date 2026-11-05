"""queries: conversione di target e trasformazioni.

Nel JSON model classico una query è un *target* piatto:

    {"refId": "A", "expr": "...", "legendFormat": "", "datasource": {"type": ..., "uid": ...}}

Nello schema v2 la stessa query è un albero:

    {"kind": "PanelQuery", "spec": {"refId": "A", "hidden": false,
      "query": {"kind": "DataQuery", "group": <tipo datasource>,
                "datasource": {"name": <uid>}, "spec": {<corpo>}, "version": "v0"}}}

La corrispondenza è esatta per tutti i campi del corpo: si sposta solo
l'involucro. `hidden` diventa `hide`, che nel classico vale `true` quando
presente.
"""
from __future__ import annotations

import copy
from typing import Any

# Versione dello schema della DataQuery prodotta in uscita.
DATA_QUERY_VERSION = "v0"

# Chiavi del target classico che non fanno parte del corpo della query.
ENVELOPE_KEYS = ("refId", "datasource", "hide")


def read_targets(panel_spec: dict[str, Any], report: Any) -> tuple[list[dict], dict]:
    """Estrae `(targets, extra)` dal `spec` di un pannello v2.

    `extra` contiene i blocchi che nel classico vivono accanto ai target
    (`queryOptions`, `transformations`) e che vanno copiati sul pannello.
    """
    data = panel_spec.get("data") or {}
    group = data.get("spec") or {}
    targets: list[dict] = []
    for query in group.get("queries") or []:
        if isinstance(query, dict):
            targets.append(_read_target(query))
    extra: dict[str, Any] = {}
    if group.get("queryOptions"):
        extra["queryOptions"] = copy.deepcopy(group["queryOptions"])
    if group.get("transformations"):
        extra["transformations"] = _read_transformations(group["transformations"])
    return targets, extra


def _read_target(query: dict[str, Any]) -> dict[str, Any]:
    """Un `PanelQuery` v2 diventa un target piatto."""
    qspec = query.get("spec") or {}
    body = ((qspec.get("query") or {}).get("spec")) or {}
    datasource = (qspec.get("query") or {}).get("datasource") or {}

    target: dict[str, Any] = copy.deepcopy(body)
    target["refId"] = qspec.get("refId", "")
    if datasource:
        target["datasource"] = {
            "type": (qspec.get("query") or {}).get("group", ""),
            "uid": datasource.get("name", ""),
        }
    if qspec.get("hidden"):
        target["hide"] = True
    return target


def write_targets(panel: dict[str, Any]) -> list[dict[str, Any]]:
    """I target di un pannello diventano `PanelQuery` v2."""
    out: list[dict[str, Any]] = []
    for target in panel.get("targets") or []:
        if not isinstance(target, dict):
            continue
        body = {
            key: copy.deepcopy(value)
            for key, value in target.items()
            if key not in ENVELOPE_KEYS
        }
        query: dict[str, Any] = {
            "kind": "DataQuery",
            "spec": body,
            "version": DATA_QUERY_VERSION,
        }
        datasource = target.get("datasource")
        if isinstance(datasource, dict):
            uid = datasource.get("uid") or datasource.get("name")
            if uid:
                query["datasource"] = {"name": uid}
            if datasource.get("type"):
                query["group"] = datasource["type"]
        elif isinstance(datasource, str) and datasource:
            query["datasource"] = {"name": datasource}
        out.append(
            {
                "kind": "PanelQuery",
                "spec": {
                    "hidden": bool(target.get("hide")),
                    "query": query,
                    "refId": target.get("refId", ""),
                },
            }
        )
    return out


def _read_transformations(items: list[Any]) -> list[dict[str, Any]]:
    """`{group, kind, spec: {options}}` → `{id, options}`."""
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        spec = item.get("spec") or {}
        out.append(
            {
                "id": item.get("group") or item.get("kind", ""),
                "options": copy.deepcopy(spec.get("options") or {}),
            }
        )
    return out


def write_transformations(items: list[Any]) -> list[dict[str, Any]]:
    """`{id, options}` → `{group, kind, spec: {options}}`."""
    out: list[dict[str, Any]] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        out.append(
            {
                "group": item.get("id", ""),
                "kind": "Transformation",
                "spec": {"options": copy.deepcopy(item.get("options") or {})},
            }
        )
    return out
