"""params: caricamento parametri da file JSON o YAML (SRP).

Astrazione per il caricamento di configurazioni parametrizzate. Supporta
JSON (stdlib) e YAML (opzionale, richiede PyYAML). I valori vuoti o nulli
vengono scartati: non sovrascrivono default né valori passati da CLI.
"""
from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import yaml  # type: ignore

    _HAS_YAML = True
except ImportError:  # pragma: no cover - dipendenza opzionale
    _HAS_YAML = False


class ParamLoader:
    """Carica parametri da un file JSON o YAML.

    Se l'estensione è .yaml/.yml e PyYAML non è installato, solleva
    ValueError. I valori None e "" vengono esclusi dal risultato.
    """

    def load(self, path: str | None) -> dict[str, Any]:
        """Ritorna i parametri dal file, oppure un dizionario vuoto se path è None."""
        if not path:
            return {}
        p = Path(path)
        if not p.exists():
            raise ValueError(f"File parametri non trovato: {path}")
        ext = p.suffix.lower()
        if ext in (".yaml", ".yml"):
            return self._load_yaml(p)
        return self._load_json(p)

    def _load_json(self, path: Path) -> dict[str, Any]:
        import json

        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        return self._clean(data)

    def _load_yaml(self, path: Path) -> dict[str, Any]:
        if not _HAS_YAML:
            raise ValueError(
                "PyYAML non installato. Usa params JSON oppure `pip install pyyaml`."
            )
        import yaml

        with path.open("r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        return self._clean(data)

    @staticmethod
    def _clean(data: Any) -> dict[str, Any]:
        """Rimuove chiavi con valore None o stringa vuota."""
        if not isinstance(data, dict):
            return {}
        return {k: v for k, v in data.items() if v is not None and v != ""}
