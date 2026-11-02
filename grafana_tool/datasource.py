"""datasource: aggiornamento dei blocchi datasource di pannelli e target (SRP).

Un'unica implementazione per `set-datasource` e `transform --uid`: evita due
copie della stessa logica e mantiene uniforme il comportamento di `--force`.
"""
from __future__ import annotations

from typing import Any


def apply_datasource(
    container: dict[str, Any],
    uid: str,
    ds_type: str | None = None,
    *,
    force: bool = False,
) -> int:
    """Imposta `datasource.uid` (e `type`) su un pannello o un target.

    - blocco `datasource` presente: aggiorna `uid` e, se indicato, `type`;
      ritorna 1.
    - blocco assente e `force=True`: crea `{"type": ds_type or "prometheus",
      "uid": uid}`; ritorna 1.
    - blocco assente e `force=False`: non fa nulla; ritorna 0.
    """
    ds = container.get("datasource")
    if isinstance(ds, dict):
        ds["uid"] = uid
        if ds_type:
            ds["type"] = ds_type
        return 1
    if force:
        container["datasource"] = {"type": ds_type or "prometheus", "uid": uid}
        return 1
    return 0


def apply_datasource_to_panel(
    panel: dict[str, Any],
    uid: str,
    ds_type: str | None = None,
    *,
    force: bool = False,
) -> int:
    """Applica `apply_datasource` al pannello e a tutti i suoi target.

    Ritorna quanti blocchi sono stati aggiornati o creati.
    """
    total = apply_datasource(panel, uid, ds_type, force=force)
    for target in panel.get("targets") or []:
        if isinstance(target, dict):
            total += apply_datasource(target, uid, ds_type, force=force)
    return total
