"""Responsabilità unica: analizzare una dashboard e produrre issue.

Il modulo definisce il tipo Issue, la classe base Rule, un set di regole
predefinite (DEFAULT_RULES) e la funzione lint() che le applica.

Ogni regola è una sottoclasse di Rule con un proprio `code` e un metodo
`check(db)` che produce zero o più Issue. Per aggiungere una regola basta
definire la classe e appenderla a DEFAULT_RULES.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Iterator

from grafana_tool.model import iter_all_panels, iter_rows, row_children

# ---------- tipi ----------

@dataclass
class Issue:
    code: str
    severity: str  # "error" | "warning" | "info"
    message: str
    panel_id: int | None = None
    row_id: int | None = None

    def as_dict(self) -> dict[str, Any]:
        d: dict[str, Any] = {
            "code": self.code,
            "severity": self.severity,
            "message": self.message,
        }
        if self.panel_id is not None:
            d["panel_id"] = self.panel_id
        if self.row_id is not None:
            d["row_id"] = self.row_id
        return d

class Rule:
    code: str = ""
    severity: str = "warning"
    description: str = ""

    def check(self, db: dict[str, Any]) -> Iterator[Issue]:
        raise NotImplementedError

# ---------- regole ----------

class MissingPanelIdRule(Rule):
    code = "MISSING_PANEL_ID"
    severity = "error"
    description = "Pannello senza campo 'id'."

    def check(self, db):
        for p in iter_all_panels(db):
            if "id" not in p:
                label = p.get("title") or p.get("type") or "?"
                yield Issue(self.code, self.severity, f"Pannello '{label}' senza id.")

class DuplicatePanelIdRule(Rule):
    code = "DUPLICATE_PANEL_ID"
    severity = "error"
    description = "ID pannello duplicato."

    def check(self, db):
        counts: dict[int, int] = {}
        for p in iter_all_panels(db):
            pid = p.get("id")
            if isinstance(pid, int):
                counts[pid] = counts.get(pid, 0) + 1
        for pid, n in counts.items():
            if n > 1:
                yield Issue(self.code, self.severity, f"ID {pid} appare {n} volte.", panel_id=pid)

class MissingTitleRule(Rule):
    code = "MISSING_TITLE"
    severity = "warning"
    description = "Pannello senza titolo."

    def check(self, db):
        for p in iter_all_panels(db):
            if p.get("type") == "row":
                continue
            if not p.get("title"):
                yield Issue(
                    self.code, self.severity,
                    f"Pannello {p.get('id', '?')} senza titolo.",
                    panel_id=p.get("id"),
                )

_NO_TARGET_TYPES = {"row", "text", "dashlist", "news", "alertlist"}

class MissingTargetsRule(Rule):
    code = "MISSING_TARGETS"
    severity = "warning"
    description = "Pannello dati senza targets."

    def check(self, db):
        for p in iter_all_panels(db):
            if p.get("type") in _NO_TARGET_TYPES:
                continue
            if not p.get("targets"):
                yield Issue(
                    self.code, self.severity,
                    f"Pannello {p.get('id', '?')} senza targets.",
                    panel_id=p.get("id"),
                )

class DuplicateQueryRule(Rule):
    code = "DUPLICATE_QUERY"
    severity = "warning"
    description = "Stessa query PromQL ripetuta in più pannelli."

    def check(self, db):
        by_expr: dict[str, list[int]] = {}
        for p in iter_all_panels(db):
            pid = p.get("id")
            if not isinstance(pid, int):
                continue
            for t in p.get("targets") or []:
                if not isinstance(t, dict):
                    continue
                expr = t.get("expr")
                if isinstance(expr, str) and expr.strip():
                    by_expr.setdefault(expr.strip(), []).append(pid)
        for expr, pids in by_expr.items():
            unique = sorted(set(pids))
            if len(unique) > 1:
                sample = expr if len(expr) <= 80 else expr[:77] + "..."
                yield Issue(
                    self.code, self.severity,
                    f"Query identica nei pannelli {unique}: {sample}",
                    panel_id=unique[0],
                )

class MissingDatasourceRule(Rule):
    code = "MISSING_DATASOURCE"
    severity = "warning"
    description = "Pannello con targets ma senza datasource esplicito."

    def check(self, db):
        for p in iter_all_panels(db):
            if not p.get("targets"):
                continue
            if p.get("datasource"):
                continue
            if any(isinstance(t, dict) and t.get("datasource") for t in p.get("targets") or []):
                continue
            yield Issue(
                self.code, self.severity,
                f"Pannello {p.get('id', '?')} senza datasource esplicito.",
                panel_id=p.get("id"),
            )

class EmptyRowRule(Rule):
    code = "EMPTY_ROW"
    severity = "warning"
    description = "Riga vuota e non collapsed."

    def check(self, db):
        for r in iter_rows(db):
            # `row_children` include i pannelli top-level delle righe espanse.
            if not row_children(db, r) and not r.get("collapsed"):
                yield Issue(
                    self.code, self.severity,
                    f"Riga {r.get('id', '?')} vuota e non collapsed.",
                    row_id=r.get("id"),
                )

class SharedLibraryPanelRule(Rule):
    code = "SHARED_LIBRARY_PANEL"
    severity = "info"
    description = "Pannello che punta a una libreria condivisa (uid globale)."

    def check(self, db):
        for p in iter_all_panels(db):
            lp = p.get("libraryPanel")
            if not isinstance(lp, dict):
                continue
            uid = lp.get("uid")
            if not uid:
                continue
            name = lp.get("name") or uid
            yield Issue(
                self.code, self.severity,
                f"Pannello {p.get('id', '?')} usa la libreria '{name}' (uid {uid}): "
                f"la copia condivide la libreria in Grafana.",
                panel_id=p.get("id"),
            )


_NUMERIC_TYPES = {"stat", "gauge", "bargauge", "graph", "timeseries"}


def _has_unit(p: dict[str, Any]) -> bool:
    fc = p.get("fieldConfig") or {}
    if isinstance(fc, dict) and (fc.get("defaults") or {}).get("unit"):
        return True
    yaxes = p.get("yaxes")
    if isinstance(yaxes, list) and yaxes and isinstance(yaxes[0], dict) and yaxes[0].get("format"):
        return True
    return False

class MissingUnitRule(Rule):
    code = "MISSING_UNIT"
    severity = "info"
    description = "Pannello numerico senza unità di misura."

    def check(self, db):
        for p in iter_all_panels(db):
            if p.get("type") not in _NUMERIC_TYPES:
                continue
            if not _has_unit(p):
                yield Issue(
                    self.code, self.severity,
                    f"Pannello {p.get('id', '?')} senza unità di misura.",
                    panel_id=p.get("id"),
                )

DEFAULT_RULES: list[Rule] = [
    MissingPanelIdRule(),
    DuplicatePanelIdRule(),
    MissingTitleRule(),
    MissingTargetsRule(),
    DuplicateQueryRule(),
    MissingDatasourceRule(),
    EmptyRowRule(),
    MissingUnitRule(),
    SharedLibraryPanelRule(),
]

# ---------- engine ----------

def lint(db: dict[str, Any], rules: list[Rule] | None = None) -> list[Issue]:
    """Applica le regole (default: DEFAULT_RULES) e ritorna le issue trovate."""
    active = rules if rules is not None else DEFAULT_RULES
    issues: list[Issue] = []
    for rule in active:
        issues.extend(rule.check(db))
    return issues
