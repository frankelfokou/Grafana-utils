"""Test di `grafana_tool.dashboard_factory`."""
from __future__ import annotations

import unittest

from grafana_tool.dashboard_factory import minimal_dashboard
from tests.support import panel


class MinimalDashboardTest(unittest.TestCase):
    def test_chiavi_obbligatorie(self):
        db = minimal_dashboard()
        for key in ("annotations", "panels", "schemaVersion", "templating", "time",
                    "timepicker", "timezone", "title", "uid", "version"):
            self.assertIn(key, db)

    def test_default(self):
        db = minimal_dashboard()
        self.assertEqual(db["title"], "Extracted row")
        self.assertEqual(db["panels"], [])
        self.assertEqual(db["templating"], {"list": []})
        self.assertIsNone(db["uid"])

    def test_titolo_e_pannelli(self):
        panels = [panel(1, "a")]
        db = minimal_dashboard(title="T", panels=panels)
        self.assertEqual(db["title"], "T")
        self.assertIs(db["panels"], panels)

    def test_eredita_contesto_dalla_sorgente(self):
        source = {
            "time": {"from": "now-6h", "to": "now"},
            "timezone": "browser",
            "refresh": "30s",
            "templating": {"list": [{"name": "product"}]},
            "schemaVersion": 39,
            "title": "sorgente",
        }
        db = minimal_dashboard(source=source)
        self.assertEqual(db["time"], {"from": "now-6h", "to": "now"})
        self.assertEqual(db["timezone"], "browser")
        self.assertEqual(db["refresh"], "30s")
        self.assertEqual(db["templating"], {"list": [{"name": "product"}]})
        self.assertEqual(db["schemaVersion"], 39)
        self.assertEqual(db["title"], "Extracted row")  # il titolo non si eredita

    def test_eredita_per_copia_profonda(self):
        source = {"time": {"from": "now-6h", "to": "now"}}
        db = minimal_dashboard(source=source)
        db["time"]["from"] = "now-1m"
        self.assertEqual(source["time"]["from"], "now-6h")


if __name__ == "__main__":
    unittest.main()
