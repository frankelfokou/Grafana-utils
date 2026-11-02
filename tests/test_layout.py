"""Test del comando `layout`: normalizzazione dei gridPos."""
from __future__ import annotations

import unittest

from grafana_tool.model import find_row, row_children
from tests.support import CLITestCase, sample_dashboard


class LayoutTest(CLITestCase):
    def test_tutte_le_righe(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("layout", src, "-o", out)
        self.assertEqual(code, 0)
        # i pannelli top-level fuori riga (100) non vengono toccati
        self.assertIn("Layout applicato a 4 pannelli.", stdout)
        db = self.read_json(out)
        # riga espansa: i figli partono sotto l'intestazione, la riga resta espansa
        self.assertFalse(find_row(db, 5)["collapsed"])
        self.assertEqual(row_children(db, find_row(db, 5))[0]["gridPos"]["y"], 1)
        # riga collassata: i figli partono da 0 e la riga resta collassata
        self.assertTrue(find_row(db, 1)["collapsed"])
        self.assertEqual(find_row(db, 1)["panels"][0]["gridPos"]["y"], 0)

    def test_su_una_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("layout", src, "--in-row", "5", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Layout applicato a 2 pannelli.", stdout)

    def test_a_capo_oltre_le_colonne(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("layout", src, "--in-row", "1", "--columns", "12", "-o", out)
        panels = find_row(self.read_json(out), 1)["panels"]
        self.assertEqual((panels[0]["gridPos"]["x"], panels[0]["gridPos"]["y"]), (0, 0))
        self.assertEqual((panels[1]["gridPos"]["x"], panels[1]["gridPos"]["y"]), (0, 8))

    def test_riga_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("layout", src, "--in-row", "999", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("non trovata", err)

    def test_colonne_non_valide(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("layout", src, "--columns", "0", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("> 0", err)


if __name__ == "__main__":
    unittest.main()
