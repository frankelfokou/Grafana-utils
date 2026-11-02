"""Test di `grafana_tool.placeholders`."""
from __future__ import annotations

import unittest

from grafana_tool.placeholders import apply_placeholders


class ApplyPlaceholdersTest(unittest.TestCase):
    def test_stringa_semplice(self):
        self.assertEqual(apply_placeholders("${NS}", {"NS": "x"}), "x")

    def test_piu_placeholder_nella_stessa_stringa(self):
        out = apply_placeholders('{namespace="${NS}",cluster_gen="${CG}"}', {"NS": "a", "CG": "2"})
        self.assertEqual(out, '{namespace="a",cluster_gen="2"}')

    def test_placeholder_ignoto_resta_invariato(self):
        self.assertEqual(apply_placeholders("${NOPE}", {"NS": "x"}), "${NOPE}")

    def test_strutture_annidate(self):
        obj = {"a": ["${NS}", {"b": "${NS}"}], "c": 1, "d": True, "e": None}
        out = apply_placeholders(obj, {"NS": "v"})
        self.assertEqual(out, {"a": ["v", {"b": "v"}], "c": 1, "d": True, "e": None})

    def test_non_modifica_l_originale(self):
        obj = {"a": "${NS}"}
        apply_placeholders(obj, {"NS": "v"})
        self.assertEqual(obj, {"a": "${NS}"})

    def test_valori_non_stringa_vengono_convertiti(self):
        self.assertEqual(apply_placeholders("${N}", {"N": 3}), "3")

    def test_nomi_placeholder_minuscoli_ignorati(self):
        self.assertEqual(apply_placeholders("${ns}", {"ns": "x"}), "${ns}")

    def test_tipi_non_stringa_preservati(self):
        self.assertEqual(apply_placeholders(42, {}), 42)
        self.assertIsNone(apply_placeholders(None, {}))


if __name__ == "__main__":
    unittest.main()
