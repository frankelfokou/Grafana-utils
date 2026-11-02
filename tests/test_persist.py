"""Test di `grafana_tool.persist`: pipeline salva + valida."""
from __future__ import annotations

import argparse
import unittest
from pathlib import Path

from grafana_tool import persist
from tests.support import CLITestCase, panel, row


def ns(**kw) -> argparse.Namespace:
    base = {"file": "in.json", "output": None, "dry_run": False,
            "severity": "error", "cmd": "test"}
    base.update(kw)
    return argparse.Namespace(**base)


class ResolveOutputTest(unittest.TestCase):
    def test_default(self):
        self.assertEqual(persist.resolve_output(ns(file="/d/dash.json")), "/d/dash_out.json")

    def test_esplicito(self):
        self.assertEqual(persist.resolve_output(ns(file="/d/dash.json", output="/o/x.json")), "/o/x.json")

    def test_attributo_assente(self):
        args = argparse.Namespace(file="/d/dash.json")
        self.assertEqual(persist.resolve_output(args), "/d/dash_out.json")


class SaveAndValidateTest(CLITestCase):
    def _input(self):
        return self.write_json("in.json", {"title": "x", "panels": [panel(1, "a")]})

    def test_successo(self):
        path = self._input()
        out = self.tmp / "out.json"
        code = persist.save_and_validate({"panels": [panel(1, "a")]}, ns(file=path, output=str(out)))
        self.assertEqual(code, 0)
        self.assertTrue(out.exists())
        self.assertEqual(self.logs(), [])

    def test_output_predefinito_accanto_all_input(self):
        path = self._input()
        code = persist.save_and_validate({"panels": [panel(1, "a")]}, ns(file=path))
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "in_out.json").exists())

    def test_errori_strutturali_rinominano_il_file(self):
        path = self._input()
        out = self.tmp / "out.json"
        code = persist.save_and_validate({"panels": [panel(1, "a"), panel(1, "b")]},
                                         ns(file=path, output=str(out)))
        self.assertEqual(code, 1)
        self.assertFalse(out.exists())
        renamed = self.tmp / "out_ERROR_VALIDATION_ERROR.json"
        self.assertTrue(renamed.exists())
        self.assertEqual(len(self.logs("validation")), 1)

    def test_lint_error_rinomina_con_suffisso_lint(self):
        path = self._input()
        out = self.tmp / "out.json"
        code = persist.save_and_validate({"panels": [panel(1)]},  # MISSING_TITLE warning
                                         ns(file=path, output=str(out), severity="warning"))
        self.assertEqual(code, 1)
        self.assertTrue((self.tmp / "out_ERROR_LINT_ERROR.json").exists())
        self.assertEqual(len(self.logs("lint")), 1)

    def test_lint_sotto_soglia_scrive_il_file_normale(self):
        path = self._input()
        out = self.tmp / "out.json"
        code = persist.save_and_validate({"panels": [panel(1)]}, ns(file=path, output=str(out)))
        self.assertEqual(code, 0)
        self.assertTrue(out.exists())

    def test_dry_run_non_scrive(self):
        path = self._input()
        out = self.tmp / "out.json"
        code = persist.save_and_validate({"panels": [panel(1, "a")]},
                                         ns(file=path, output=str(out), dry_run=True))
        self.assertEqual(code, 0)
        self.assertFalse(out.exists())

    def test_dry_run_con_errori_indica_il_nome_ipotetico(self):
        path = self._input()
        out = self.tmp / "out.json"
        import io
        from contextlib import redirect_stdout

        buf = io.StringIO()
        with redirect_stdout(buf):
            code = persist.save_and_validate({"panels": [panel(1), panel(1)]},
                                             ns(file=path, output=str(out), dry_run=True))
        self.assertEqual(code, 1)
        self.assertIn("out_ERROR_VALIDATION_ERROR.json", buf.getvalue())

    def test_riga_vuota_collassata_non_e_un_errore(self):
        path = self._input()
        out = self.tmp / "out.json"
        db = {"panels": [row(1, "R", collapsed=True, panels=[panel(2, "a")])]}
        self.assertEqual(persist.save_and_validate(db, ns(file=path, output=str(out))), 0)
        self.assertTrue(Path(out).exists())


if __name__ == "__main__":
    unittest.main()
