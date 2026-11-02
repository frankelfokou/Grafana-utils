"""Test di `grafana_tool.io`: caricamento, salvataggio e nomi di default."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from grafana_tool.io import (
    InputError,
    OutputError,
    default_output_path,
    load_dashboard,
    save_dashboard,
    with_suffix,
)


class TempDirCase(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)


class LoadDashboardTest(TempDirCase):
    def test_carica_oggetto_json(self):
        path = self.tmp / "d.json"
        path.write_text('{"title": "x", "panels": []}', encoding="utf-8")
        self.assertEqual(load_dashboard(str(path)), {"title": "x", "panels": []})

    def test_file_inesistente(self):
        with self.assertRaises(InputError):
            load_dashboard(str(self.tmp / "nope.json"))

    def test_directory_al_posto_del_file(self):
        with self.assertRaises(InputError):
            load_dashboard(str(self.tmp))

    def test_json_malformato(self):
        path = self.tmp / "bad.json"
        path.write_text("{non-json", encoding="utf-8")
        with self.assertRaises(InputError) as ctx:
            load_dashboard(str(path))
        self.assertIn("JSON non valido", str(ctx.exception))

    def test_radice_non_oggetto(self):
        path = self.tmp / "list.json"
        path.write_text("[1, 2, 3]", encoding="utf-8")
        with self.assertRaises(InputError) as ctx:
            load_dashboard(str(path))
        self.assertIn("non è un oggetto", str(ctx.exception))

    def test_input_error_e_value_error(self):
        # La CLI distingue InputError prima di ValueError: l'ordine conta.
        self.assertTrue(issubclass(InputError, ValueError))
        self.assertTrue(issubclass(OutputError, ValueError))


class SaveDashboardTest(TempDirCase):
    def test_scrive_creando_le_directory(self):
        out = self.tmp / "a" / "b" / "out.json"
        save_dashboard({"title": "x"}, str(out))
        self.assertTrue(out.exists())
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {"title": "x"})

    def test_serializzazione_leggibile_con_newline_finale(self):
        out = self.tmp / "out.json"
        save_dashboard({"a": 1, "b": "à"}, str(out))
        text = out.read_text(encoding="utf-8")
        self.assertTrue(text.endswith("\n"))
        self.assertIn("\n  \"a\": 1,", text)
        self.assertIn("à", text)  # ensure_ascii=False

    def test_sovrascrive_un_file_esistente(self):
        out = self.tmp / "out.json"
        out.write_text("vecchio", encoding="utf-8")
        save_dashboard({"nuovo": True}, str(out))
        self.assertEqual(json.loads(out.read_text(encoding="utf-8")), {"nuovo": True})

    def test_dry_run_non_tocca_il_disco(self):
        out = self.tmp / "out.json"
        save_dashboard({"a": 1}, str(out), dry_run=True)
        self.assertFalse(out.exists())

    def test_output_su_directory_solleva_output_error(self):
        with self.assertRaises(OutputError):
            save_dashboard({"a": 1}, str(self.tmp))


class NomiTest(unittest.TestCase):
    def test_default_output_path(self):
        self.assertEqual(default_output_path("dashboard.json"), "dashboard_out.json")
        self.assertEqual(default_output_path("/tmp/a/dash.json"), "/tmp/a/dash_out.json")
        self.assertEqual(default_output_path("dash"), "dash_out.json")

    def test_with_suffix(self):
        self.assertEqual(
            with_suffix("dashboard_out.json", "_ERROR_LINT_ERROR"),
            "dashboard_out_ERROR_LINT_ERROR.json",
        )
        self.assertEqual(with_suffix("dash", "_ERROR_X"), "dash_ERROR_X.json")


if __name__ == "__main__":
    unittest.main()
