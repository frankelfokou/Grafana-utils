"""dashboard_factory: factory per costruire dashboard Grafana minime (SRP).

Centralizza la creazione di oggetti dashboard vuoti o minimi, evitando che
ogni comando duplichi lo schema hardcoded delle chiavi obbligatorie
(annotations, schemaVersion, time, ecc.).
"""
from __future__ import annotations

import copy
from typing import Any


_SOURCE_KEYS = ("time", "timezone", "refresh", "templating", "schemaVersion")


def minimal_dashboard(
    title: str = "Extracted row",
    panels: list[dict[str, Any]] | None = None,
    source: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Costruisce una dashboard minima contenente i pannelli indicati.

    Usata ad esempio da `extract-row` per incapsulare una singola row
    estratta da una dashboard sorgente. Se `source` è indicata, la
    dashboard eredita intervallo temporale, fuso e variabili della sorgente,
    così i pannelli estratti mantengono lo stesso contesto di esecuzione.
    """
    db: dict[str, Any] = {
        "annotations": {"list": []},
        "editable": True,
        "graphTooltip": 0,
        "id": None,
        "links": [],
        "panels": panels or [],
        "refresh": "",
        "schemaVersion": 38,
        "style": "dark",
        "tags": [],
        "templating": {"list": []},
        "time": {"from": "now-1h", "to": "now"},
        "timepicker": {},
        "timezone": "",
        "title": title,
        "uid": None,
        "version": 1,
        "weekStart": "",
    }
    if isinstance(source, dict):
        for key in _SOURCE_KEYS:
            if key in source:
                db[key] = copy.deepcopy(source[key])
    return db
