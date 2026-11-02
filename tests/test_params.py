"""Test di `grafana_tool.params`."""
from __future__ import annotations

import json
import tempfile
import unittest
from pathlib import Path

from grafana_tool.params import ParamLoader

try:  # dipendenza opzionale
    import yaml  # noqa: F401

    HAS_YAML = True
except ImportError:  # pragma: no cover
    HAS_YAML = False


class ParamLoaderTest(unittest.TestCase):
    def setUp(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.tmp = Path(self._tmp.name)
        self.addCleanup(self._tmp.cleanup)
        self.loader = ParamLoader()

    def test_path_none_ritorna_vuoto(self):
        self.assertEqual(self.loader.load(None), {})
        self.assertEqual(self.loader.load(""), {})

    def test_json(self):
        path = self.tmp / "p.json"
        path.write_text(json.dumps({"NS": "a", "CG": "2"}), encoding="utf-8")
        self.assertEqual(self.loader.load(str(path)), {"NS": "a", "CG": "2"})

    def test_scarta_valori_vuoti(self):
        path = self.tmp / "p.json"
        path.write_text(json.dumps({"A": "", "B": None, "C": "x", "D": 0}), encoding="utf-8")
        self.assertEqual(self.loader.load(str(path)), {"C": "x", "D": 0})

    def test_file_inesistente(self):
        with self.assertRaises(ValueError) as ctx:
            self.loader.load(str(self.tmp / "nope.json"))
        self.assertIn("non trovato", str(ctx.exception))

    def test_json_non_oggetto_ritorna_vuoto(self):
        path = self.tmp / "p.json"
        path.write_text("[1, 2]", encoding="utf-8")
        self.assertEqual(self.loader.load(str(path)), {})

    @unittest.skipUnless(HAS_YAML, "PyYAML non installato")
    def test_yaml(self):
        path = self.tmp / "p.yml"
        path.write_text("NS: a\nCG: 2\nVUOTO: ''\n", encoding="utf-8")
        self.assertEqual(self.loader.load(str(path)), {"NS": "a", "CG": 2})

    def test_yaml_senza_pyyaml_solleva(self):
        if HAS_YAML:  # pragma: no cover
            self.skipTest("PyYAML installato")
        path = self.tmp / "p.yml"
        path.write_text("NS: a\n", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx:
            self.loader.load(str(path))
        self.assertIn("PyYAML", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
