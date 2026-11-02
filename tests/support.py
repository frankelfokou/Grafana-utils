"""Fixture condivise e helper per i test di grafana-tool.

Contiene:
  - builder di pannelli, righe e dashboard usati da più moduli di test;
  - `CLITestCase`, che isola i log in una directory temporanea e fornisce
    un runner per invocare la CLI con `main(argv)`.
"""
from __future__ import annotations

import io
import json
import os
import tempfile
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parent.parent
EXAMPLES = REPO_ROOT / "examples"
PRODUCTION_DASHBOARD = EXAMPLES / "full_dashbaord.json"
TEMPLATE = REPO_ROOT / "templates" / "system-view.row.tpl.json"

PROM_DS = {"type": "prometheus", "uid": "uid-prom"}


def panel(pid: int, title: str | None = None, typ: str = "timeseries", **extra: Any) -> dict[str, Any]:
    """Pannello minimo, con datasource e una query valida."""
    p: dict[str, Any] = {
        "id": pid,
        "type": typ,
        "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
        "datasource": dict(PROM_DS),
        "targets": [{"expr": f"up{{panel=\"{pid}\"}}", "datasource": dict(PROM_DS)}],
    }
    if title is not None:
        p["title"] = title
    p.update(extra)
    return p


def row(row_id: int, title: str, collapsed: bool = True, panels: list | None = None) -> dict[str, Any]:
    """Riga `type=row`; `panels` sono i figli annidati."""
    r: dict[str, Any] = {
        "id": row_id,
        "type": "row",
        "title": title,
        "collapsed": collapsed,
        "gridPos": {"h": 1, "w": 24, "x": 0, "y": 0},
        "panels": panels or [],
    }
    return r


def sample_dashboard() -> dict[str, Any]:
    """Dashboard con entrambe le rappresentazioni delle righe.

    `panels`::

        [0] 100   text    pannello top-level, fuori riga
        [1] row 1         collassata, 2 figli annidati (2, 3)
        [2] row 5         espansa, nessun figlio annidato
        [3] 6             top-level: appartiene alla riga 5
        [4] 7             top-level: appartiene alla riga 5
        [5] row 9         collassata e vuota
    """
    r1 = row(1, "Row A", collapsed=True, panels=[panel(2, "A1"), panel(3, "A2")])
    r5 = row(5, "Row B", collapsed=False)
    r9 = row(9, "Row Empty", collapsed=True)
    return {
        "title": "Fixture",
        "schemaVersion": 38,
        "panels": [
            panel(100, "NOTE", typ="text"),
            r1,
            r5,
            panel(6, "B1"),
            panel(7, "B2"),
            r9,
        ],
    }


def legacy_dashboard() -> dict[str, Any]:
    """Schema legacy: i pannelli delle righe stanno in `rows`."""
    return {
        "title": "Legacy",
        "rows": [
            {"id": 1, "title": "Legacy row", "panels": [panel(2, "L1")]},
        ],
    }


class CLITestCase(unittest.TestCase):
    """Base per i test: log isolati e runner della CLI."""

    def setUp(self) -> None:
        self._tmpdir = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmpdir.name)
        self._prev_log_dir = os.environ.get("GRAFANA_TOOL_LOG_DIR")
        os.environ["GRAFANA_TOOL_LOG_DIR"] = str(self.tmp / "logs")
        self.addCleanup(self._tmpdir.cleanup)

    def tearDown(self) -> None:
        if self._prev_log_dir is None:
            os.environ.pop("GRAFANA_TOOL_LOG_DIR", None)
        else:
            os.environ["GRAFANA_TOOL_LOG_DIR"] = self._prev_log_dir

    # ---------- helper ----------

    def run_cli(self, *argv: str) -> tuple[int, str, str]:
        """Invoca `cli.main(argv)` e ritorna `(exit_code, stdout, stderr)`."""
        from grafana_tool import cli

        out, err = io.StringIO(), io.StringIO()
        with redirect_stdout(out), redirect_stderr(err):
            try:
                code = cli.main([str(a) for a in argv])
            except SystemExit as e:  # argparse esce per --help/--version/error
                code = e.code if isinstance(e.code, int) else 1
        return int(code), out.getvalue(), err.getvalue()

    def write_json(self, name: str, obj: Any) -> str:
        path = self.tmp / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")
        return str(path)

    def read_json(self, path: str | Path) -> Any:
        return json.loads(Path(path).read_text(encoding="utf-8"))

    def logs(self, kind: str | None = None) -> list[Path]:
        """Log scritti in questa sessione di test (eventualmente filtrati per tipo)."""
        directory = self.tmp / "logs"
        if not directory.is_dir():
            return []
        files = sorted(directory.iterdir())
        if kind:
            files = [f for f in files if f.name.startswith(f"{kind}_error_")]
        return files


def content_panels(db: dict[str, Any]) -> list[dict[str, Any]]:
    """Pannelli di contenuto di primo livello (comodo nelle asserzioni)."""
    return [p for p in db.get("panels") or [] if p.get("type") != "row"]


def all_ids(db: dict[str, Any]) -> list[int]:
    """Tutti gli ID presenti, righe e annidati compresi."""
    ids: list[int] = []
    stack = list(db.get("panels") or []) + list(db.get("rows") or [])
    while stack:
        item = stack.pop()
        if isinstance(item, dict):
            if isinstance(item.get("id"), int):
                ids.append(item["id"])
            stack.extend(item.get("panels") or [])
    return sorted(ids)
