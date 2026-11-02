"""Responsabilità unica: parsing e applicazione delle sostituzioni testuali.

Non conosce la dashboard come concetto: lavora su singoli pannelli e su
dizionari {old: new}.
"""
from __future__ import annotations

from typing import Any

def parse_replacements(items: list[str] | None) -> dict[str, str]:
    """Converte una lista di stringhe 'OLD=NEW' in un dizionario.

    Solleva ValueError se un elemento non contiene '='.
    """
    out: dict[str, str] = {}
    for it in items or []:
        if "=" not in it:
            raise ValueError(f"--replace richiede OLD=NEW, ricevuto: {it!r}")
        old, new = it.split("=", 1)
        out[old] = new
    return out

def apply_in_panel(panel: dict[str, Any], repl: dict[str, str]) -> int:
    """Applica le sostituzioni a target[*].expr. Ritorna il numero di target modificati."""
    if not repl:
        return 0
    changed = 0
    for t in panel.get("targets") or []:
        if not isinstance(t, dict):
            continue
        expr = t.get("expr")
        if not isinstance(expr, str):
            continue
        new = expr
        for old, new_val in repl.items():
            new = new.replace(old, new_val)
        if new != expr:
            t["expr"] = new
            changed += 1
    return changed
