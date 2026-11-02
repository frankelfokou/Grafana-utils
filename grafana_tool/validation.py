"""Responsabilità unica: validare una dashboard (struttura + lint).

`check(db, threshold)` esegue i controlli strutturali e il linter, e
restituisce un `Result` con:

  - `errors`: problemi strutturali (ID duplicati o mancanti);
  - `issues`: tutte le issue del linter;
  - `failing`: se la validazione è da considerarsi fallita;
  - `kind`: il tipo di errore da registrare (`validation` o `lint`).

La pipeline di scrittura (`persist.py`) e il comando `validate` usano lo
stesso codice, così l'esito è identico in entrambi i percorsi.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from grafana_tool.linter import Issue, lint
from grafana_tool.model import iter_all_panels, iter_rows

SEV_ORDER = {"info": 1, "warning": 2, "error": 3}
SEV_LABEL = {"info": "INFO", "warning": "WARN", "error": "ERR"}


def blocking_issues(issues: list[Issue], threshold: str) -> list[Issue]:
    """Issue con severità pari o superiore alla soglia."""
    limit = SEV_ORDER[threshold]
    return [i for i in issues if SEV_ORDER[i.severity] >= limit]


def issue_lines(issues: list[Issue]) -> list[str]:
    """Righe di dettaglio per il log, nello stesso formato del report."""
    return [f"[{i.code}] {i.severity}: {i.message}" for i in issues]


def failure_details(result: "Result") -> list[str]:
    """Dettagli da registrare nel log quando `result` è fallita."""
    return list(result.errors) + issue_lines(result.blocking)


@dataclass
class Result:
    """Esito della validazione di una dashboard."""

    errors: list[str]
    issues: list[Issue]
    threshold: str = "error"

    @property
    def blocking(self) -> list[Issue]:
        """Issue che superano la soglia configurata."""
        return blocking_issues(self.issues, self.threshold)

    @property
    def failing(self) -> bool:
        return bool(self.errors) or bool(self.blocking)

    @property
    def kind(self) -> Optional[str]:
        """Tipo di errore da registrare, None se la validazione passa."""
        if self.errors:
            return "validation"
        if self.blocking:
            return "lint"
        return None

    def counts(self) -> dict[str, int]:
        out = {"info": 0, "warning": 0, "error": 0}
        for i in self.issues:
            out[i.severity] = out.get(i.severity, 0) + 1
        return out


def structural_errors(db: dict[str, Any]) -> list[str]:
    """Controlla gli ID di tutti i pannelli, righe comprese."""
    panels = list(iter_all_panels(db))
    int_ids = [p["id"] for p in panels if isinstance(p.get("id"), int)]
    dupes = sorted({i for i in int_ids if int_ids.count(i) > 1})
    missing = [p for p in panels if "id" not in p]

    errors: list[str] = []
    if dupes:
        errors.append(f"ID duplicati: {dupes}")
    if missing:
        errors.append(f"{len(missing)} pannelli senza campo 'id'.")
    return errors


def check(db: dict[str, Any], threshold: str = "error") -> Result:
    """Esegue controlli strutturali e lint sulla dashboard in memoria."""
    return Result(structural_errors(db), lint(db), threshold)


def summary(db: dict[str, Any]) -> str:
    """Riepilogo di conteggio, con righe e pannelli distinti."""
    rows = len(list(iter_rows(db)))
    panels = len([p for p in iter_all_panels(db) if p.get("type") != "row"])
    return f"righe: {rows}, pannelli: {panels}"


def render(result: Result, show_all: bool = True) -> list[str]:
    """Righe di report per un `Result`."""
    lines: list[str] = []

    if result.errors:
        lines.append("Validazione: FALLITA")
        lines.extend(f"  ERRORE: {e}" for e in result.errors)
    else:
        lines.append("Validazione: nessun errore strutturale.")

    counts = result.counts()
    total = len(result.issues)
    lines.append(
        f"Lint: {total} issue "
        f"({counts['error']} error, {counts['warning']} warning, {counts['info']} info) "
        f"- soglia: {result.threshold}"
    )
    shown = result.issues if show_all else result.blocking
    for i in shown:
        lines.append(f"  {SEV_LABEL[i.severity]} [{i.code}] {i.message}")
    return lines
