"""selection: criteri condivisi per selezionare i pannelli (SRP).

`prune` e `transform` filtrano i pannelli con le stesse due regole:
tipo confrontato senza distinzione di maiuscole e titolo come regex
case-insensitive. Qui vivono una volta sola, così il comportamento di
`--match-type` e `--match-title` è identico in tutti i comandi.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

from grafana_tool.model import title_regex


def _fold(value: Any) -> str:
    """Forma di confronto per i tipi di pannello (case-insensitive)."""
    return str(value or "").casefold()


@dataclass(frozen=True)
class PanelMatcher:
    """Criterio di selezione su tipo e/o titolo di un pannello.

    Un criterio vuoto non matcha nulla: i comandi che lo richiedono devono
    verificare `any()` e fallire con un messaggio d'uso.
    """

    panel_type: str | None = None
    title: re.Pattern[str] | None = field(default=None, compare=False)

    @classmethod
    def from_args(
        cls, match_type: str | None = None, match_title: str | None = None
    ) -> "PanelMatcher":
        """Costruisce il criterio dalle opzioni `--match-type` / `--match-title`."""
        return cls(
            panel_type=match_type,
            title=title_regex(match_title) if match_title else None,
        )

    def any(self) -> bool:
        """Vero se almeno un criterio è impostato."""
        return self.panel_type is not None or self.title is not None

    def matches(self, panel: dict[str, Any]) -> bool:
        """Vero se il pannello soddisfa tutti i criteri impostati."""
        if not self.any():
            return False
        if self.panel_type is not None and _fold(panel.get("type")) != _fold(self.panel_type):
            return False
        if self.title is not None and not self.title.search(panel.get("title") or ""):
            return False
        return True
