"""Test di `grafana_tool.namespace_normalizer`."""
from __future__ import annotations

import unittest

from grafana_tool.namespace_normalizer import normalize_namespace


class NormalizeNamespaceTest(unittest.TestCase):
    def test_riscrive_il_match_esatto(self):
        expr = 'up{namespace="pa-digital"}'
        self.assertEqual(normalize_namespace(expr), 'up{namespace=~"pa-digital"}')

    def test_lascia_invariato_il_regex(self):
        expr = 'up{namespace=~"pa-digital"}'
        self.assertEqual(normalize_namespace(expr), expr)

    def test_ignora_stringhe_senza_parentesi_graffe(self):
        self.assertEqual(normalize_namespace('namespace="x"'), 'namespace="x"')

    def test_ignora_stringhe_senza_namespace(self):
        self.assertEqual(normalize_namespace('up{job="x"}'), 'up{job="x"}')

    def test_riscrive_tutte_le_occorrenze(self):
        expr = '{namespace="a"} or {namespace="b"}'
        self.assertEqual(normalize_namespace(expr), '{namespace=~"a"} or {namespace=~"b"}')

    def test_strutture_annidate(self):
        obj = {"t": [{"expr": 'up{namespace="a"}'}], "n": 1}
        out = normalize_namespace(obj)
        self.assertEqual(out["t"][0]["expr"], 'up{namespace=~"a"}')
        self.assertEqual(out["n"], 1)

    def test_non_modifica_l_originale(self):
        obj = {"expr": 'up{namespace="a"}'}
        normalize_namespace(obj)
        self.assertEqual(obj["expr"], 'up{namespace="a"}')


if __name__ == "__main__":
    unittest.main()
