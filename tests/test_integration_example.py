"""Test di integrazione sulla dashboard di produzione in `examples/`.

La dashboard reale contiene la riga "VITA - VISTA PV - Sistemistica" (l'ultima)
in forma **espansa**: `row["panels"]` è vuoto e i 16 pannelli sono top-level
subito dopo la riga. Questo è il caso che il tool deve saper estrarre.
"""
from __future__ import annotations

import hashlib
import json
import unittest

from grafana_tool.model import (
    find_row,
    get_max_id,
    iter_all_panels,
    iter_rows,
    row_children,
)
from tests.support import CLITestCase, PRODUCTION_DASHBOARD

ROW_ID = 125
ROW_TITLE = "VITA - VISTA PV - Sistemistica --> GEN2"


def digest(path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


class ProductionDashboardTest(CLITestCase):
    @classmethod
    def setUpClass(cls):
        cls.source = json.loads(PRODUCTION_DASHBOARD.read_text(encoding="utf-8"))

    def test_la_riga_sistemistica_e_l_ultima_ed_e_espansa(self):
        rows = list(iter_rows(self.source))
        self.assertEqual(rows[-1]["id"], ROW_ID)
        self.assertEqual(rows[-1]["title"], ROW_TITLE)
        self.assertFalse(rows[-1]["collapsed"])
        self.assertEqual(rows[-1]["panels"], [])

    def test_row_children_trova_i_16_pannelli(self):
        riga = find_row(self.source, ROW_ID)
        figli = row_children(self.source, riga)
        self.assertEqual(len(figli), 16)
        self.assertEqual(figli[0]["title"], "POD RESTART")

    def test_list_rows_conta_i_pannelli_della_riga_espansa(self):
        code, out, _ = self.run_cli("list", "row", str(PRODUCTION_DASHBOARD))
        self.assertEqual(code, 0)
        linea = next(line for line in out.splitlines() if str(ROW_ID) in line)
        self.assertIn("16", linea)

    def test_extract_row_estrae_la_row_con_tutti_i_pannelli(self):
        out = self.tmp / "sistemistica.json"
        before = digest(PRODUCTION_DASHBOARD)

        code, stdout, _ = self.run_cli(
            "extract", "row", str(PRODUCTION_DASHBOARD),
            "--match-title", "Sistemistica", "-o", out,
        )
        self.assertEqual(code, 0, stdout)
        self.assertEqual(digest(PRODUCTION_DASHBOARD), before, "l'input non deve cambiare")

        estratta = self.read_json(out)
        panels = estratta["panels"]
        riga, pannelli = panels[0], panels[1:]

        # la riga estratta
        self.assertEqual(riga["type"], "row")
        self.assertEqual(riga["title"], ROW_TITLE)
        self.assertFalse(riga["collapsed"])
        self.assertEqual(riga["panels"], [])

        # tutti e soli i 16 pannelli della riga
        attesi = row_children(self.source, find_row(self.source, ROW_ID))
        self.assertEqual([p["title"] for p in pannelli], [p["title"] for p in attesi])
        self.assertEqual(len(pannelli), 16)

        # query e datasource preservati
        for estratto, originale in zip(pannelli, attesi):
            self.assertEqual(estratto.get("targets"), originale.get("targets"))
            self.assertEqual(estratto.get("datasource"), originale.get("datasource"))

        # ID rinumerati e unici, con base successiva all'ultimo id della sorgente:
        # nel file di output non compaiono gli id già usati in Grafana.
        ids = [p["id"] for p in panels]
        base = get_max_id(self.source) + 1
        self.assertEqual(ids, list(range(base, base + 17)))
        self.assertFalse(set(ids) & {p.get("id") for p in iter_all_panels(self.source)})

        # gridPos normalizzata: la riga a y=0, i pannelli subito sotto
        self.assertEqual(riga["gridPos"]["y"], 0)
        self.assertEqual(min(p["gridPos"]["y"] for p in pannelli), 1)

        # contesto temporale e variabili ereditati dalla sorgente
        self.assertEqual(estratta["time"], self.source["time"])
        self.assertEqual(estratta["templating"], self.source["templating"])

    def test_la_dashboard_estratta_valida(self):
        out = self.tmp / "sistemistica.json"
        self.run_cli("extract", "row", str(PRODUCTION_DASHBOARD),
                     "--match-title", "Sistemistica", "-o", out)
        code, stdout, _ = self.run_cli("validate", str(out))
        self.assertEqual(code, 0, stdout)
        self.assertNotIn("FALLITA", stdout)

    def test_extract_con_id(self):
        out = self.tmp / "per-id.json"
        code, _, _ = self.run_cli("extract", "row", str(PRODUCTION_DASHBOARD),
                                  "--id", str(ROW_ID), "-o", out)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.read_json(out)["panels"]), 17)

    def test_la_dashboard_estratta_ha_i_pannelli_attesi_per_titolo(self):
        out = self.tmp / "sistemistica.json"
        self.run_cli("extract", "row", str(PRODUCTION_DASHBOARD),
                     "--match-title", "Sistemistica", "-o", out)
        titoli = [p.get("title") for p in self.read_json(out)["panels"][1:]]
        for atteso in ("POD RESTART", "TOTAL POD NUMBER", "Mem % Usage", "Pod CPU% Usage"):
            self.assertIn(atteso, titoli)

    def test_replace_limitato_alla_row_sistemistica(self):
        out = self.tmp / "replace.json"
        code, stdout, _ = self.run_cli(
            "update", "row", str(PRODUCTION_DASHBOARD),
            "--id", str(ROW_ID),
            "--replace", 'cluster_gen="2"=cluster_gen="3"', "-o", out,
        )
        self.assertEqual(code, 0, stdout)
        self.assertIn("modifiche al contenuto", stdout)
        db = self.read_json(out)
        self.assertIn('cluster_gen=\\"3\\"', json.dumps(db))

    def test_create_row_dalla_row_espansa(self):
        out = self.tmp / "dup.json"
        code, stdout, _ = self.run_cli("create", "row", str(PRODUCTION_DASHBOARD),
                                       "--from-id", str(ROW_ID), "-o", out)
        self.assertEqual(code, 0, stdout)
        self.assertIn("con 16 pannelli", stdout)
        db = self.read_json(out)
        copia = db["panels"][-1]
        self.assertEqual(len(copia["panels"]), 16)
        self.assertTrue(copia["collapsed"])

    def test_validate_dashboard_di_produzione(self):
        code, out, _ = self.run_cli("validate", str(PRODUCTION_DASHBOARD))
        self.assertEqual(code, 0)
        self.assertIn("righe: 6, pannelli: 90", out)


if __name__ == "__main__":
    unittest.main()
