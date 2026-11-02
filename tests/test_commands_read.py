"""Test dei comandi read-only: `list`, `validate`, `lint`."""
from __future__ import annotations

import json
import unittest

from tests.support import CLITestCase, panel, row, sample_dashboard


class ListRowTest(CLITestCase):
    def test_elenca_le_righe(self):
        src = self.write_json("in.json", sample_dashboard())
        code, out, _ = self.run_cli("list", "row", src)
        self.assertEqual(code, 0)
        self.assertIn("Titolo", out)
        self.assertIn("Row A", out)
        self.assertIn("Row B", out)
        self.assertIn("Row Empty", out)

    def test_conta_i_pannelli_delle_righe_espanse(self):
        src = self.write_json("in.json", sample_dashboard())
        _, out, _ = self.run_cli("list", "row", src)
        riga_b = next(line for line in out.splitlines() if "Row B" in line)
        # Row B è espansa: i pannelli 6 e 7 sono top-level ma le appartengono
        self.assertEqual(riga_b.split()[-2:], ["2", "False"])

    def test_dashboard_senza_righe(self):
        src = self.write_json("in.json", {"panels": [panel(1, "a")]})
        code, out, _ = self.run_cli("list", "row", src)
        self.assertEqual(code, 0)
        self.assertIn("Nessuna riga trovata.", out)

    def test_riga_senza_titolo(self):
        r = row(1, "")
        r.pop("title")
        src = self.write_json("in.json", {"panels": [r]})
        _, out, _ = self.run_cli("list", "row", src)
        self.assertIn("(senza titolo)", out)

    def test_filtro_per_id(self):
        src = self.write_json("in.json", sample_dashboard())
        _, out, _ = self.run_cli("list", "row", src, "--id", "9")
        self.assertIn("Row Empty", out)
        self.assertNotIn("Row A", out)

    def test_filtro_per_titolo_case_insensitive(self):
        src = self.write_json("in.json", sample_dashboard())
        _, out, _ = self.run_cli("list", "row", src, "--match-title", "row a")
        self.assertIn("Row A", out)
        self.assertNotIn("Row B", out)

    def test_json(self):
        src = self.write_json("in.json", sample_dashboard())
        code, out, _ = self.run_cli("list", "row", src, "--format", "json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual([r["id"] for r in payload], [1, 5, 9])
        self.assertEqual(payload[1]["panel_count"], 2)
        self.assertFalse(payload[1]["collapsed"])


class ListPanelTest(CLITestCase):
    def test_elenca_tutti_i_pannelli_con_la_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        code, out, _ = self.run_cli("list", "panel", src)
        self.assertEqual(code, 0)
        self.assertIn("- [100] text: NOTE  (nessuna riga)", out)
        self.assertIn("- [2] timeseries: A1  (riga 1)", out)
        self.assertIn("- [6] timeseries: B1  (riga 5)", out)

    def test_le_righe_non_compaiono(self):
        src = self.write_json("in.json", sample_dashboard())
        _, out, _ = self.run_cli("list", "panel", src)
        self.assertNotIn("[5]", out)
        self.assertNotIn("[1] timeseries", out)

    def test_filtro_per_riga_espansa(self):
        src = self.write_json("in.json", sample_dashboard())
        code, out, _ = self.run_cli("list", "panel", src, "--in-row", "5")
        self.assertEqual(code, 0)
        self.assertIn("[6]", out)
        self.assertIn("[7]", out)
        self.assertNotIn("[100]", out)
        self.assertNotIn("[2]", out)

    def test_riga_vuota(self):
        src = self.write_json("in.json", sample_dashboard())
        code, out, _ = self.run_cli("list", "panel", src, "--in-row", "9")
        self.assertEqual(code, 0)
        self.assertIn("Nessun pannello trovato.", out)

    def test_riga_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("list", "panel", src, "--in-row", "999")
        self.assertEqual(code, 1)
        self.assertIn("non trovata", err)
        self.assertEqual(len(self.logs("command")), 1)

    def test_filtro_per_tipo(self):
        src = self.write_json("in.json", sample_dashboard())
        _, out, _ = self.run_cli("list", "panel", src, "--match-type", "text")
        self.assertIn("[100]", out)
        self.assertNotIn("[2]", out)

    def test_expr_troncata(self):
        p = panel(1, "lunga")
        p["targets"][0]["expr"] = "x" * 200
        src = self.write_json("in.json", {"panels": [p]})
        _, out, _ = self.run_cli("list", "panel", src)
        self.assertIn("...", out)
        self.assertNotIn("x" * 150, out)

    def test_json(self):
        src = self.write_json("in.json", sample_dashboard())
        code, out, _ = self.run_cli("list", "panel", src, "--format", "json")
        self.assertEqual(code, 0)
        by_id = {p["id"]: p for p in json.loads(out)}
        self.assertEqual(by_id[6]["row_id"], 5)
        self.assertIsNone(by_id[100]["row_id"])
        self.assertEqual(by_id[100]["type"], "text")

    def test_id_di_una_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("list", "panel", src, "--id", "1")
        self.assertEqual(code, 1)
        self.assertIn("usare il tipo `row`", err)


class ValidateTest(CLITestCase):
    def test_dashboard_valida(self):
        src = self.write_json("in.json", {"panels": [row(1, "R", panels=[panel(2, "a")])]})
        code, out, _ = self.run_cli("validate", src)
        self.assertEqual(code, 0)
        self.assertIn("Validazione: nessun errore strutturale.", out)
        self.assertIn("righe: 1, pannelli: 1", out)
        self.assertEqual(self.logs(), [])

    def test_errori_strutturali(self):
        src = self.write_json("in.json", {"panels": [panel(1, "a"), panel(1, "b")]})
        code, out, _ = self.run_cli("validate", src)
        self.assertEqual(code, 1)
        self.assertIn("Validazione: FALLITA", out)
        self.assertEqual(len(self.logs("validation")), 1)

    def test_soglia_warning(self):
        src = self.write_json("in.json", {"panels": [panel(1)]})
        code, _, _ = self.run_cli("validate", src, "--severity", "warning")
        self.assertEqual(code, 1)
        self.assertEqual(len(self.logs("lint")), 1)

    def test_soglia_info(self):
        src = self.write_json("in.json", {"panels": [panel(1, "ok", typ="stat")]})
        code, _, _ = self.run_cli("validate", src, "--severity", "info")
        self.assertEqual(code, 1)


class LintTest(CLITestCase):
    def _db(self):
        return {"panels": [panel(1), panel(2, "ok", typ="table")]}

    def test_formato_text(self):
        src = self.write_json("in.json", self._db())
        code, out, _ = self.run_cli("lint", src)
        self.assertEqual(code, 0)  # solo warning/info
        self.assertIn("[MISSING_TITLE]", out)
        self.assertIn("Totale:", out)

    def test_formato_json(self):
        src = self.write_json("in.json", self._db())
        code, out, _ = self.run_cli("lint", src, "--format", "json")
        self.assertEqual(code, 0)
        issues = json.loads(out)
        self.assertTrue(all({"code", "severity", "message"} <= set(i) for i in issues))

    def test_formato_json_resta_parsabile_in_caso_di_errore(self):
        src = self.write_json("in.json", {"panels": [{"id": 1, "type": "stat"}]})
        code, out, err = self.run_cli("lint", src, "--format", "json", "--severity", "info")
        self.assertEqual(code, 1)
        self.assertIsInstance(json.loads(out), list)
        self.assertIn("Log:", err)

    def test_dashboard_pulita(self):
        db = {"panels": [row(1, "R", panels=[panel(2, "ok", typ="stat",
                                                   fieldConfig={"defaults": {"unit": "short"}})])]}
        src = self.write_json("in.json", db)
        code, out, _ = self.run_cli("lint", src)
        self.assertEqual(code, 0)
        self.assertIn("Nessuna issue trovata", out)

    def test_soglia_info_blocca(self):
        src = self.write_json("in.json", self._db())
        code, _, _ = self.run_cli("lint", src, "--severity", "info")
        self.assertEqual(code, 1)
        self.assertEqual(len(self.logs("lint")), 1)


if __name__ == "__main__":
    unittest.main()
