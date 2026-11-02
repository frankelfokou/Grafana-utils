"""Test di `grafana_tool.replacements`."""
from __future__ import annotations

import unittest

from grafana_tool.replacements import apply_in_panel, parse_replacements


class ParseReplacementsTest(unittest.TestCase):
    def test_lista_vuota(self):
        self.assertEqual(parse_replacements([]), {})
        self.assertEqual(parse_replacements(None), {})

    def test_singola_sostituzione(self):
        self.assertEqual(parse_replacements(["a=b"]), {"a": "b"})

    def test_taglia_al_primo_uguale(self):
        self.assertEqual(parse_replacements(["a=b=c"]), {"a": "b=c"})

    def test_valore_vuoto_ammesso(self):
        self.assertEqual(parse_replacements(["token="]), {"token": ""})

    def test_senza_uguale_solleva(self):
        with self.assertRaises(ValueError) as ctx:
            parse_replacements(["senza-uguale"])
        self.assertIn("OLD=NEW", str(ctx.exception))

    def test_multiple(self):
        self.assertEqual(parse_replacements(["a=b", "c=d"]), {"a": "b", "c": "d"})


class ApplyInPanelTest(unittest.TestCase):
    def _panel(self, *exprs):
        return {"id": 1, "targets": [{"expr": e} for e in exprs]}

    def test_sostituisce_in_tutti_i_target(self):
        p = self._panel("up{ns=\"a\"}", "down{ns=\"a\"}")
        self.assertEqual(apply_in_panel(p, {"ns=\"a\"": "ns=\"b\""}), 2)
        self.assertEqual([t["expr"] for t in p["targets"]], ["up{ns=\"b\"}", "down{ns=\"b\"}"])

    def test_conta_solo_i_target_modificati(self):
        p = self._panel("aaa", "bbb")
        self.assertEqual(apply_in_panel(p, {"aaa": "zzz"}), 1)

    def test_sostituzioni_multiple_in_ordine(self):
        p = self._panel("abc")
        apply_in_panel(p, {"a": "b", "b": "c"})
        self.assertEqual(p["targets"][0]["expr"], "ccc")

    def test_senza_sostituzioni(self):
        p = self._panel("abc")
        self.assertEqual(apply_in_panel(p, {}), 0)
        self.assertEqual(p["targets"][0]["expr"], "abc")

    def test_ignora_target_non_dict_e_expr_non_stringa(self):
        p = {"targets": ["x", {"expr": 42}, {"expr": "abc"}]}
        self.assertEqual(apply_in_panel(p, {"abc": "z"}), 1)

    def test_pannello_senza_target(self):
        self.assertEqual(apply_in_panel({"id": 1}, {"a": "b"}), 0)


if __name__ == "__main__":
    unittest.main()
