"""namespace_normalizer: riscrittura namespace="x" → namespace=~"x" nelle query PromQL (SRP).

Tocca solo stringhe che contengono sia "{" che "namespace=". Non modifica
campi non-query (es. testo libero) a meno che non contengano entrambi i
marker.
"""
from __future__ import annotations

import re
from typing import Any

NAMESPACE_EXACT_RE = re.compile(r'namespace="')


def normalize_namespace(obj: Any) -> Any:
    """Riscrive namespace=\"x\" in namespace=~\"x\" dentro stringhe PromQL.

    Tocca solo stringhe che contengono sia "{" che "namespace=".
    Le stringhe già in forma regex (namespace=~) vengono lasciate invariate.
    """
    if isinstance(obj, dict):
        return {k: normalize_namespace(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [normalize_namespace(v) for v in obj]
    if isinstance(obj, str) and "namespace=" in obj and "{" in obj:
        return NAMESPACE_EXACT_RE.sub('namespace=~"', obj)
    return obj
