"""dashboard: conversione dell'involucro della dashboard.

Riguarda tutto ciò che sta *fuori* da righe e pannelli:

  classico (`panels`/`rows`)              schema v2
  --------------------------------------  ------------------------------------
  title, tags, editable, links            title, tags, editable, links
  time {from, to}                         timeSettings {from, to}
  timezone                                timeSettings.timezone
  refresh                                 timeSettings.autoRefresh
  timepicker {refresh_intervals, hidden}  timeSettings.autoRefreshIntervals/hideTimepicker
  fiscalYearStartMonth                    timeSettings.fiscalYearStartMonth
  annotations.list[]                      annotations[]
  cursorSync, preload, liveNow            cursorSync, preload, liveNow

`uid`, `id` e `version` non esistono nello schema v2: in uscita vengono
rimossi e la perdita è dichiarata nel report.
"""
from __future__ import annotations

import copy
from typing import Any

# Campi della dashboard che lo schema v2 non conosce.
V2_ABSENT_KEYS = ("uid", "id", "version")

# Campi v2 conservati a parte nel modello canonico (`_extras`).
EXTRA_KEYS = ("cursorSync", "preload", "liveNow")

# Chiavi dell'annotazione che restano fuori dal corpo della query.
ANNOTATION_ENVELOPE = ("name", "enable", "hide", "iconColor", "datasource", "builtIn")


def read_into(v2: dict[str, Any], db: dict[str, Any], report: Any) -> None:
    """Copia titolo, tag, tempo, annotazioni, link e extra nel canonico."""
    db["title"] = v2.get("title") or ""
    if "tags" in v2:
        db["tags"] = copy.deepcopy(v2["tags"])
    if "editable" in v2:
        db["editable"] = v2["editable"]
    if v2.get("links"):
        db["links"] = copy.deepcopy(v2["links"])

    _read_time(v2.get("timeSettings") or {}, db)

    annotations = v2.get("annotations")
    if annotations:
        db["annotations"] = {"list": [_read_annotation(a) for a in annotations
                                      if isinstance(a, dict)]}

    extras = {k: copy.deepcopy(v2[k]) for k in EXTRA_KEYS if k in v2}
    if extras:
        db["_extras"] = extras


def write_into(db: dict[str, Any], out: dict[str, Any], report: Any) -> None:
    """Copia titolo, tag, tempo, annotazioni, link e extra nello schema v2."""
    out["title"] = db.get("title") or ""
    out["tags"] = copy.deepcopy(db.get("tags") or [])
    out["editable"] = db.get("editable", True)
    out["links"] = copy.deepcopy(db.get("links") or [])
    out["timeSettings"] = _write_time(db)
    out["annotations"] = [
        _write_annotation(a, report) for a in _annotation_list(db) if isinstance(a, dict)
    ]
    out.update(copy.deepcopy(db.get("_extras") or {}))

    for key in V2_ABSENT_KEYS:
        if key in db and db[key] is not None:
            report.add(
                "lossy", f"'{key}' non esiste nello schema v2: rimosso in uscita"
            )


# --- tempo -----------------------------------------------------------------


def _read_time(settings: dict[str, Any], db: dict[str, Any]) -> None:
    """`timeSettings` v2 → campi tempo del classico."""
    if not settings:
        return
    if "from" in settings or "to" in settings:
        db["time"] = {
            "from": settings.get("from", "now-6h"),
            "to": settings.get("to", "now"),
        }
    if "timezone" in settings:
        db["timezone"] = settings["timezone"]
    if "autoRefresh" in settings:
        db["refresh"] = settings["autoRefresh"]
    if "fiscalYearStartMonth" in settings:
        db["fiscalYearStartMonth"] = settings["fiscalYearStartMonth"]

    picker: dict[str, Any] = {}
    if "autoRefreshIntervals" in settings:
        picker["refresh_intervals"] = copy.deepcopy(settings["autoRefreshIntervals"])
    if "hideTimepicker" in settings:
        picker["hidden"] = bool(settings["hideTimepicker"])
    if picker:
        db["timepicker"] = picker


def _write_time(db: dict[str, Any]) -> dict[str, Any]:
    """Campi tempo del classico → `timeSettings` v2."""
    time = db.get("time") or {}
    picker = db.get("timepicker") or {}
    settings: dict[str, Any] = {}
    if time or "time" in db:
        settings["from"] = time.get("from", "now-6h")
        settings["to"] = time.get("to", "now")
    if "timezone" in db:
        settings["timezone"] = db["timezone"]
    settings["autoRefresh"] = db.get("refresh", "")
    if "refresh_intervals" in picker:
        settings["autoRefreshIntervals"] = copy.deepcopy(picker["refresh_intervals"])
    if "hidden" in picker:
        settings["hideTimepicker"] = bool(picker["hidden"])
    if "fiscalYearStartMonth" in db:
        settings["fiscalYearStartMonth"] = db["fiscalYearStartMonth"]
    return settings


# --- annotazioni -----------------------------------------------------------


def _annotation_list(db: dict[str, Any]) -> list[Any]:
    """Lista delle annotazioni, in entrambe le forme classiche."""
    annotations = db.get("annotations")
    if isinstance(annotations, dict):
        items = annotations.get("list")
        return items if isinstance(items, list) else []
    if isinstance(annotations, list):
        return annotations
    return []


def _read_annotation(annotation: dict[str, Any]) -> dict[str, Any]:
    """Un'annotazione v2 diventa un elemento di `annotations.list`."""
    spec = annotation.get("spec") or {}
    query = spec.get("query") or {}
    body = query.get("spec") or {}

    out = {
        key: copy.deepcopy(value)
        for key, value in spec.items()
        if key != "query"
    }
    if query:
        out["datasource"] = {
            "type": query.get("group", ""),
            "uid": (query.get("datasource") or {}).get("name", ""),
        }
        out.update(copy.deepcopy(body))
    return out


def _write_annotation(annotation: dict[str, Any], report: Any = None) -> dict[str, Any]:
    """Un elemento di `annotations.list` diventa un'annotazione v2."""
    body = {
        key: copy.deepcopy(value)
        for key, value in annotation.items()
        if key not in ANNOTATION_ENVELOPE
    }
    # Il classico più recente annida la query in `target`; lo schema v2 la
    # tiene piatta. L'appiattimento è dichiarato invece che silenzioso.
    target = body.pop("target", None)
    if isinstance(target, dict):
        if report is not None:
            report.add(
                "lossy",
                f"annotazione '{annotation.get('name', '?')}': 'target' "
                "appiattito nel corpo della query",
            )
        body = {**copy.deepcopy(target), **body}
    datasource = annotation.get("datasource") or {}
    query: dict[str, Any] = {"kind": "DataQuery", "spec": body, "version": "v0"}
    if datasource.get("uid"):
        query["datasource"] = {"name": datasource["uid"]}
    if datasource.get("type"):
        query["group"] = datasource["type"]

    spec = {
        key: copy.deepcopy(value)
        for key, value in annotation.items()
        if key in ANNOTATION_ENVELOPE and key != "datasource"
    }
    spec["query"] = query
    return {"kind": "AnnotationQuery", "spec": spec}
