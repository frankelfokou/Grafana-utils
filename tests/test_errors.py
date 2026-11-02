"""Test di `grafana_tool.errors`: suffissi e log su file."""
from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from grafana_tool import errors


class SuffixTest(unittest.TestCase):
    def test_suffissi(self):
        self.assertEqual(errors.suffix("validation"), "_ERROR_VALIDATION_ERROR")
        self.assertEqual(errors.suffix("lint"), "_ERROR_LINT_ERROR")

    def test_tipi_sconosciuti(self):
        with self.assertRaises(KeyError):
            errors.suffix("boh")


class LogDirTest(unittest.TestCase):
    def test_default(self):
        prev = __import__("os").environ.pop(errors.LOG_DIR_ENV, None)
        try:
            self.assertEqual(errors.log_dir(), __import__("os").path.join(".", "out"))
            self.assertEqual(errors.log_dir("/base"), "/base/out")
        finally:
            if prev is not None:
                __import__("os").environ[errors.LOG_DIR_ENV] = prev

    def test_override_assoluto(self):
        prev = __import__("os").environ.get(errors.LOG_DIR_ENV)
        __import__("os").environ[errors.LOG_DIR_ENV] = "/tmp/logs-x"
        try:
            self.assertEqual(errors.log_dir(), "/tmp/logs-x")
        finally:
            if prev is None:
                __import__("os").environ.pop(errors.LOG_DIR_ENV, None)
            else:
                __import__("os").environ[errors.LOG_DIR_ENV] = prev


class LogErrorTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        import os

        self._prev = os.environ.get(errors.LOG_DIR_ENV)
        os.environ[errors.LOG_DIR_ENV] = str(self.tmp / "out")
        self.addCleanup(self._restore)

    def _restore(self):
        import os

        if self._prev is None:
            os.environ.pop(errors.LOG_DIR_ENV, None)
        else:
            os.environ[errors.LOG_DIR_ENV] = self._prev

    def test_scrive_il_log_con_i_dettagli(self):
        path = errors.log_error(
            "lint",
            "2 issue",
            command="lint",
            argv=["lint", "d.json"],
            exit_code=1,
            details=["[X] error: boom"],
        )
        self.assertIsNotNone(path)
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("type: LINT_ERROR", text)
        self.assertIn("command: lint", text)
        self.assertIn("argv: lint d.json", text)
        self.assertIn("exit_code: 1", text)
        self.assertIn("message: 2 issue", text)
        self.assertIn("  [X] error: boom", text)
        self.assertTrue(Path(path).name.startswith("lint_error_"))

    def test_log_senza_dettagli(self):
        path = errors.log_error("input", "non trovato", exit_code=2)
        text = Path(path).read_text(encoding="utf-8")
        self.assertIn("type: INPUT_ERROR", text)
        self.assertNotIn("details:", text)

    def test_nomi_unici_nello_stesso_secondo(self):
        first = errors.log_error("input", "a")
        second = errors.log_error("input", "b")
        self.assertNotEqual(first, second)
        self.assertTrue(Path(second).stem.endswith("-2"))

    def test_ritorna_none_se_non_puo_scrivere(self):
        blocker = self.tmp / "blocco"
        blocker.write_text("x", encoding="utf-8")
        import os

        os.environ[errors.LOG_DIR_ENV] = str(blocker / "sub")
        self.assertIsNone(errors.log_error("input", "x"))


if __name__ == "__main__":
    unittest.main()
