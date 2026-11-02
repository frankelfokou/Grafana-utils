"""placeholders: motore di sostituzione ricorsiva ${CHIAVE} (SRP).

Sostituisce i placeholder della forma ${NOME} in ogni stringa di un albero
JSON. I placeholder non presenti nel mapping vengono lasciati invariati.
Nessuna conoscenza del dominio Grafana: lavora su strutture dati generiche.
"""
from __future__ import annotations

import re
from typing import Any

PLACEHOLDER_RE = re.compile(r"\$\{([A-Z_]+)\}")


def apply_placeholders(obj: Any, mapping: dict[str, str]) -> Any:
    """Sostituisce ricorsivamente ${CHIAVE} in ogni stringa di un albero JSON.

    I placeholder non presenti in `mapping` vengono lasciati invariati.
    I non-string (int, bool, None, dict, list) vengono preservati.
    """
    if isinstance(obj, dict):
        return {k: apply_placeholders(v, mapping) for k, v in obj.items()}
    if isinstance(obj, list):
        return [apply_placeholders(v, mapping) for v in obj]
    if isinstance(obj, str):
        def _sub(m: "re.Match[str]") -> str:
            key = m.group(1)
            return str(mapping[key]) if key in mapping else m.group(0)
        return PLACEHOLDER_RE.sub(_sub, obj)
    return obj
