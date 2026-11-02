"""Responsabilità unica: classificare gli errori e registrarli su file.

Ogni errore prodotto da un comando del pacchetto ha un tipo (`input`,
`output`, `validation`, `lint`, `command`, `usage`). Il tipo determina:

  - il suffisso da appendere al nome del file di output quando una scrittura
    va a buon fine ma la validazione finale fallisce (`_ERROR_LINT_ERROR`, ...);
  - il nome del file di log in `out/`, nella forma
    `<tipo>_error_<data>.txt`.

Il modulo non conosce la CLI né il dominio Grafana.
"""
from __future__ import annotations

import os
from datetime import datetime
from typing import Iterable, Optional

LOG_DIR = "out"
LOG_DIR_ENV = "GRAFANA_TOOL_LOG_DIR"

ERROR_KINDS = {
    "input": "INPUT_ERROR",
    "output": "OUTPUT_ERROR",
    "validation": "VALIDATION_ERROR",
    "lint": "LINT_ERROR",
    "command": "COMMAND_ERROR",
    "usage": "USAGE_ERROR",
}


def suffix(kind: str) -> str:
    """Suffisso da appendere al nome del file di output per il tipo dato."""
    return f"_ERROR_{ERROR_KINDS[kind]}"


def log_dir(base: str = ".") -> str:
    """Percorso della cartella dei log.

    La variabile d'ambiente `GRAFANA_TOOL_LOG_DIR` permette di spostarla
    (usata dai test per non sporcare la cartella di lavoro). Un path
    relativo viene risolto rispetto a `base`, come il default `out`.
    """
    override = os.environ.get(LOG_DIR_ENV)
    if override:
        return override if os.path.isabs(override) else os.path.join(base, override)
    return os.path.join(base, LOG_DIR)


def _unique_path(path: str) -> str:
    """Evita di sovrascrivere un log creato nello stesso secondo."""
    if not os.path.exists(path):
        return path
    root, ext = os.path.splitext(path)
    i = 2
    while os.path.exists(f"{root}-{i}{ext}"):
        i += 1
    return f"{root}-{i}{ext}"


def log_error(
    kind: str,
    message: str,
    *,
    command: Optional[str] = None,
    argv: Optional[Iterable[str]] = None,
    exit_code: Optional[int] = None,
    details: Optional[Iterable[str]] = None,
) -> Optional[str]:
    """Scrive il log dell'errore in `out/` e restituisce il path.

    Restituisce None se il file non è stato scritto: un log mancante non deve
    mai mascherare l'errore originale.
    """
    try:
        directory = log_dir()
        os.makedirs(directory, exist_ok=True)
        stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
        path = _unique_path(os.path.join(directory, f"{kind}_error_{stamp}.txt"))

        lines = [
            f"timestamp: {datetime.now().isoformat(timespec='seconds')}",
            f"type: {ERROR_KINDS[kind]}",
        ]
        if command:
            lines.append(f"command: {command}")
        if argv:
            lines.append("argv: " + " ".join(str(a) for a in argv))
        if exit_code is not None:
            lines.append(f"exit_code: {exit_code}")
        lines.append(f"message: {message}")
        if details:
            lines.append("")
            lines.append("details:")
            lines.extend(f"  {d}" for d in details)

        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines) + "\n")
        return path
    except OSError:
        return None
