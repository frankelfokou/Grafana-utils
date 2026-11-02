"""Test di `grafana_tool.datasource`: aggiornamento blocchi datasource."""
from __future__ import annotations

import unittest

from grafana_tool.datasource import apply_datasource, apply_datasource_to_panel


class ApplyDatasourceTest(unittest.TestCase):
    def test_aggiorna_blocco_esistente(self):
        container = {"datasource": {"type": "prometheus", "uid": "vecchio"}}
        self.assertEqual(apply_datasource(container, "nuovo"), 1)
        self.assertEqual(container["datasource"], {"type": "prometheus", "uid": "nuovo"})

    def test_aggiorna_anche_il_tipo(self):
        container = {"datasource": {"type": "prometheus", "uid": "vecchio"}}
        self.assertEqual(apply_datasource(container, "nuovo", "loki"), 1)
        self.assertEqual(container["datasource"], {"type": "loki", "uid": "nuovo"})

    def test_blocco_assente_senza_force_viene_saltato(self):
        container = {}
        self.assertEqual(apply_datasource(container, "nuovo"), 0)
        self.assertNotIn("datasource", container)

    def test_blocco_assente_con_force_viene_creato(self):
        container = {}
        self.assertEqual(apply_datasource(container, "nuovo", force=True), 1)
        self.assertEqual(container["datasource"], {"type": "prometheus", "uid": "nuovo"})

    def test_force_usa_il_tipo_indicato(self):
        container = {}
        apply_datasource(container, "nuovo", "loki", force=True)
        self.assertEqual(container["datasource"]["type"], "loki")


class ApplyDatasourceToPanelTest(unittest.TestCase):
    def test_aggiorna_pannello_e_target(self):
        panel = {
            "datasource": {"type": "prometheus", "uid": "vecchio"},
            "targets": [
                {"datasource": {"type": "prometheus", "uid": "vecchio"}},
                {"expr": "up"},
            ],
        }
        self.assertEqual(apply_datasource_to_panel(panel, "nuovo", force=True), 3)
        self.assertEqual(panel["datasource"]["uid"], "nuovo")
        self.assertEqual(panel["targets"][0]["datasource"]["uid"], "nuovo")
        self.assertEqual(panel["targets"][1]["datasource"]["uid"], "nuovo")

    def test_ignora_target_non_dict(self):
        panel = {"targets": [None, "x"]}
        self.assertEqual(apply_datasource_to_panel(panel, "nuovo", force=True), 1)
        self.assertEqual(panel["datasource"]["uid"], "nuovo")


if __name__ == "__main__":
    unittest.main()
