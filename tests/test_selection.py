"""Test di `grafana_tool.selection`: criteri condivisi tra prune e transform."""
from __future__ import annotations

import unittest

from grafana_tool.selection import PanelMatcher
from tests.support import panel


class PanelMatcherTest(unittest.TestCase):
    def test_criterio_vuoto_non_matcha_nulla(self):
        matcher = PanelMatcher.from_args()
        self.assertFalse(matcher.any())
        self.assertFalse(matcher.matches(panel(1, "A")))

    def test_solo_tipo(self):
        matcher = PanelMatcher.from_args("timeseries")
        self.assertTrue(matcher.any())
        self.assertTrue(matcher.matches(panel(1, "A")))
        self.assertFalse(matcher.matches(panel(2, "B", typ="text")))

    def test_tipo_case_insensitive(self):
        self.assertTrue(PanelMatcher.from_args("TIMESERIES").matches(panel(1, "A")))

    def test_tipo_assente_nel_pannello(self):
        self.assertFalse(PanelMatcher.from_args("timeseries").matches({"id": 1, "title": "A"}))

    def test_titolo_come_regex_case_insensitive(self):
        matcher = PanelMatcher.from_args(match_title="^b1$")
        self.assertTrue(matcher.matches(panel(1, "B1")))
        self.assertFalse(matcher.matches(panel(2, "B10")))

    def test_pannello_senza_titolo(self):
        self.assertFalse(PanelMatcher.from_args(match_title=".").matches({"id": 1}))

    def test_tipo_e_titolo_sono_in_and(self):
        matcher = PanelMatcher.from_args("timeseries", "^b")
        self.assertTrue(matcher.matches(panel(1, "B1")))
        self.assertFalse(matcher.matches(panel(2, "A1")))
        self.assertFalse(matcher.matches(panel(3, "B1", typ="text")))

    def test_regex_non_valida_e_un_errore_di_comando(self):
        """Una regex scritta male non deve arrivare all'utente come traceback."""
        with self.assertRaises(ValueError) as ctx:
            PanelMatcher.from_args(match_title="[")
        self.assertIn("espressione regolare non valida", str(ctx.exception))


if __name__ == "__main__":
    unittest.main()
