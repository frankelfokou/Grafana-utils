"""Responsabilità unica: leggere e scrivere il file JSON della dashboard.

Contratto I/O esplicito:
  - load_dashboard: il file di input DEVE esistere ed essere un JSON oggetto,
    altrimenti solleva InputError.
  - save_dashboard: se il file di output non esiste lo crea (incluse le
    directory genitore), se esiste lo sovrascrive, se il path è invalido
    solleva OutputError. Con dry_run=True non tocca il disco.

Il modulo non conosce la semantica di Grafana: si limita alla serializzazione.
"""
from __future__ import annotations

import json
import os
from typing import Any

class InputError(ValueError):
    """Errore sul file di input (non esiste, non leggibile, JSON non valido)."""

class OutputError(ValueError):
    """Errore sul file di output (path invalido, directory non creabile, non scrivibile)."""

def load_json(path: str) -> Any:
    """Carica un file JSON di qualsiasi forma (oggetto, lista, scalare).

    Solleva InputError se il file non esiste, non è un file regolare, non è
    JSON valido o non è leggibile. Non impone vincoli sulla radice: serve ai
    file accessori (es. inventario delle dashboard), non alle dashboard.
    """
    if not os.path.exists(path):
        raise InputError(f"file di input non trovato: {path}")
    if not os.path.isfile(path):
        raise InputError(f"il percorso di input non è un file: {path}")
    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except json.JSONDecodeError as e:
        raise InputError(f"JSON non valido in {path}: {e}") from e
    except OSError as e:
        raise InputError(f"impossibile leggere {path}: {e}") from e


def load_dashboard(path: str) -> dict[str, Any]:
    """Carica il file JSON di input.

    Solleva InputError se il file non esiste, non è un file regolare,
    non è JSON valido o la radice non è un oggetto.
    """
    data = load_json(path)
    if not isinstance(data, dict):
        raise InputError(f"{path}: la radice del JSON non è un oggetto.")
    return data

def save_dashboard(db: dict[str, Any], path: str, dry_run: bool = False) -> None:
    """Scrive la dashboard su `path`.

    - Se `dry_run` è True non scrive nulla.
    - Se la directory genitore non esiste, la crea.
    - Se `path` esiste lo sovrascrive; altrimenti lo crea.
    - Solleva OutputError se il path punta a una directory o non è scrivibile.
    """
    if dry_run:
        print(f"[dry-run] Nessun file scritto ({path}).")
        return
    if os.path.isdir(path):
        raise OutputError(f"il percorso di output è una directory: {path}")
    parent = os.path.dirname(os.path.abspath(path))
    if not os.path.isdir(parent):
        try:
            os.makedirs(parent, exist_ok=True)
        except OSError as e:
            raise OutputError(f"impossibile creare la directory {parent}: {e}") from e
    try:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(db, f, indent=2, ensure_ascii=False)
            f.write("\n")
    except OSError as e:
        raise OutputError(f"impossibile scrivere {path}: {e}") from e
    print(f"Scritto: {path}")


def default_output_path(path: str) -> str:
    """Nome di output da usare quando `-o` è omesso.

    `dashboard.json` → `dashboard_out.json`, nella stessa directory.
    Il file di input non viene mai sovrascritto.
    """
    root, ext = os.path.splitext(path)
    return f"{root}_out{ext or '.json'}"


def with_suffix(path: str, suffix: str) -> str:
    """Inserisce `suffix` prima dell'estensione.

    `dashboard_out.json` + `_ERROR_LINT_ERROR` →
    `dashboard_out_ERROR_LINT_ERROR.json`.
    """
    root, ext = os.path.splitext(path)
    return f"{root}{suffix}{ext or '.json'}"

