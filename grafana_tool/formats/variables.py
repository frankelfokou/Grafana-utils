"""variables: conversione delle variabili (templating).

Classico: `templating.list[]` con `type` testuale (`query`, `datasource`,
`custom`, ...). Schema v2: `variables[]` con `kind` in CamelCase
(`QueryVariable`, `DatasourceVariable`, ...) e il resto dentro `spec`.

La mappa tra i due vocabolari è esplicita: se compare un `kind` che non
conosciamo il campo viene conservato e la perdita dichiarata, invece di
essere ignorata.
"""
from __future__ import annotations

import copy
from typing import Any

KIND_TO_TYPE = {
    "DatasourceVariable": "datasource",
    "QueryVariable": "query",
    "TextBoxVariable": "textbox",
    "ConstantVariable": "constant",
    "CustomVariable": "custom",
    "IntervalVariable": "interval",
    "AdHocVariable": "adhoc",
    "SystemVariable": "system",
    "SwitchVariable": "switch",
}

TYPE_TO_KIND = {value: key for key, value in KIND_TO_TYPE.items()}

# Versione dello schema della DataQuery delle variabili.
DATA_QUERY_VERSION = "v0"

# Enum delle variabili: il JSON classico usa numeri, lo schema v2 stringhe.
# Scriverne una forma nell'altro formato non è un dettaglio estetico: Grafana
# legge `hide` come numero, quindi `"dontHide"` non vale 0 e l'etichetta del
# selettore sparisce.
HIDE = {0: "dontHide", 1: "hideLabel", 2: "hideVariable"}
REFRESH = {0: "never", 1: "onDashboardLoad", 2: "onTimeRangeChanged"}
SORT = {
    0: "disabled",
    1: "alphabeticalAsc",
    2: "alphabeticalDesc",
    3: "numericalAsc",
    4: "numericalDesc",
    5: "alphabeticalCaseInsensitiveAsc",
    6: "alphabeticalCaseInsensitiveDesc",
    7: "naturalAsc",
    8: "naturalDesc",
}
ENUMS = {"hide": HIDE, "refresh": REFRESH, "sort": SORT}


def to_classic_enums(spec: dict[str, Any]) -> None:
    """Porta gli enum testuali sulla forma numerica del classico."""
    for key, mapping in ENUMS.items():
        by_name = {name: number for number, name in mapping.items()}
        value = spec.get(key)
        if isinstance(value, str) and value in by_name:
            spec[key] = by_name[value]


def to_v2_enums(spec: dict[str, Any]) -> None:
    """Porta gli enum numerici sulla forma testuale di v2."""
    for key, mapping in ENUMS.items():
        value = spec.get(key)
        if isinstance(value, int) and not isinstance(value, bool) and value in mapping:
            spec[key] = mapping[value]


def read_into(v2: dict[str, Any], db: dict[str, Any], report: Any) -> None:
    """`variables[]` v2 → `templating.list[]` classico."""
    variables = v2.get("variables")
    if not variables:
        return
    db["templating"] = {
        "list": [_read_variable(v, report) for v in variables if isinstance(v, dict)]
    }


def write_into(db: dict[str, Any], out: dict[str, Any], report: Any) -> None:
    """`templating.list[]` classico → `variables[]` v2."""
    out["variables"] = [
        _write_variable(v, report) for v in _variable_list(db) if isinstance(v, dict)
    ]


def _variable_list(db: dict[str, Any]) -> list[Any]:
    """Lista delle variabili, in entrambe le forme classiche."""
    templating = db.get("templating")
    if isinstance(templating, dict):
        items = templating.get("list")
        return items if isinstance(items, list) else []
    if isinstance(templating, list):
        return templating
    return []


def _read_variable(variable: dict[str, Any], report: Any) -> dict[str, Any]:
    """Una variabile v2 diventa una voce di `templating.list`."""
    kind = variable.get("kind") or ""
    spec = copy.deepcopy(variable.get("spec") or {})
    name = spec.get("name", "?")

    vtype = KIND_TO_TYPE.get(kind)
    if vtype is None:
        report.add(
            "partial",
            f"variabile '{name}': kind '{kind}' non mappato, conservato com'è",
        )
        vtype = kind

    if kind == "DatasourceVariable":
        spec["query"] = spec.pop("pluginId", "")
    elif kind == "QueryVariable":
        _read_query_variable(spec, name, report)

    to_classic_enums(spec)
    spec["type"] = vtype
    return spec


def _read_query_variable(
    spec: dict[str, Any], name: str, report: Any
) -> None:
    """Appiattisce la `DataQuery` di una variabile di query."""
    query = spec.get("query")
    if not isinstance(query, dict):
        return
    datasource = query.get("datasource") or {}
    if datasource.get("name"):
        spec["datasource"] = {
            "type": query.get("group", ""),
            "uid": datasource["name"],
        }
    body = query.get("spec")
    if isinstance(body, dict):
        # Il classico accetta due forme: la stringa e l'oggetto {query, refId}.
        # Una corpo con la sola chiave `query` viene dalla stringa, quindi si
        # torna alla stringa: altrimenti un giro classico→v2→classico
        # cambierebbe la forma della variabile senza cambiarne il senso.
        if set(body) == {"query"}:
            spec["query"] = body["query"]
        else:
            spec["query"] = copy.deepcopy(body)
    else:
        report.add(
            "partial",
            f"variabile '{name}': query senza corpo, conservata la forma originale",
        )
        spec["query"] = copy.deepcopy(query)


def _write_variable(variable: dict[str, Any], report: Any) -> dict[str, Any]:
    """Una voce di `templating.list` diventa una variabile v2."""
    spec = copy.deepcopy(variable)
    vtype = spec.pop("type", "")
    kind = TYPE_TO_KIND.get(vtype)
    if kind is None:
        report.add(
            "partial",
            f"variabile '{variable.get('name', '?')}': tipo '{vtype}' non mappato, "
            "conservato com'è",
        )
        kind = vtype

    if vtype == "datasource":
        spec["pluginId"] = spec.pop("query", "")
    elif vtype == "query":
        _write_query_variable(spec, variable.get("name", "?"), report)

    to_v2_enums(spec)
    return {"kind": kind, "spec": spec}


def _write_query_variable(
    spec: dict[str, Any], name: str, report: Any
) -> None:
    """Ricostruisce la `DataQuery` di una variabile di query."""
    body = spec.get("query")
    datasource = spec.pop("datasource", None)
    inner = copy.deepcopy(body) if isinstance(body, dict) else {"query": body}
    query: dict[str, Any] = {
        "kind": "DataQuery",
        "spec": inner,
        "version": DATA_QUERY_VERSION,
    }
    if isinstance(datasource, dict) and datasource.get("uid"):
        query["datasource"] = {"name": datasource["uid"]}
        if datasource.get("type"):
            query["group"] = datasource["type"]
    else:
        report.add(
            "lossy",
            f"variabile '{name}': nessun datasource nel classico, "
            "la query v2 resta senza datasource",
        )
    spec["query"] = query
