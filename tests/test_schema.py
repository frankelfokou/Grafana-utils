"""Test del riconoscimento del formato e dei metadati interni."""
from __future__ import annotations

import unittest

from grafana_tool import schema
from grafana_tool.io import InputError

from tests.support import legacy_dashboard, sample_dashboard


class DetectTest(unittest.TestCase):
    def test_classico(self) -> None:
        self.assertEqual(schema.detect({"panels": []}), schema.CLASSIC)
        self.assertEqual(schema.detect({"rows": []}), schema.CLASSIC)

    def test_v2(self) -> None:
        self.assertEqual(
            schema.detect({"elements": {}, "layout": {}}), schema.V2
        )

    def test_sconosciuto(self) -> None:
        self.assertEqual(schema.detect({"title": "x"}), schema.UNKNOWN)
        self.assertEqual(schema.detect({}), schema.UNKNOWN)

    def test_elementi_senza_layout_non_bastano(self) -> None:
        self.assertEqual(schema.detect({"elements": {}}), schema.UNKNOWN)


class RequireRecognizedTest(unittest.TestCase):
    def test_riconosce_il_classico(self) -> None:
        self.assertEqual(
            schema.require_recognized(sample_dashboard()), schema.CLASSIC
        )

    def test_formato_sconosciuto_solleva_input_error(self) -> None:
        with self.assertRaises(InputError) as ctx:
            schema.require_recognized({"title": "x"}, command="list")
        message = str(ctx.exception)
        self.assertIn("formato non riconosciuto", message)
        self.assertIn("list", message)

    def test_il_messaggio_elenca_i_marcatori(self) -> None:
        with self.assertRaises(InputError) as ctx:
            schema.require_recognized({})
        self.assertIn("panels", str(ctx.exception))
        self.assertIn("elements", str(ctx.exception))


class EnsureTabsTest(unittest.TestCase):
    def test_aggiunge_un_tab_con_il_titolo_della_dashboard(self) -> None:
        db = sample_dashboard()
        schema.ensure_tabs(db)
        self.assertEqual(db["_tabs"], [{"id": 1, "title": "Fixture"}])

    def test_assegna_ogni_riga_al_tab_implicito(self) -> None:
        db = sample_dashboard()
        schema.ensure_tabs(db)
        self.assertTrue(all(schema.tab_of(r) == 1 for r in db["panels"]
                            if r.get("type") == "row"))

    def test_e_idempotente(self) -> None:
        db = sample_dashboard()
        schema.ensure_tabs(db, title="Primo")
        schema.ensure_tabs(db, title="Secondo")
        self.assertEqual(len(db["_tabs"]), 1)
        self.assertEqual(db["_tabs"][0]["title"], "Primo")

    def test_righe_legacy(self) -> None:
        db = legacy_dashboard()
        schema.ensure_tabs(db)
        self.assertEqual(db["rows"][0]["_tab"], 1)


class StripInternalTest(unittest.TestCase):
    def test_rimuove_le_chiavi_di_servizio(self) -> None:
        db = sample_dashboard()
        schema.ensure_tabs(db)
        db["panels"][1]["_element"] = "panel-1"
        schema.strip_internal(db)
        self.assertNotIn("_tabs", db)
        self.assertNotIn("_tab", db["panels"][1])
        self.assertNotIn("_element", db["panels"][1])

    def test_non_tocca_le_chiavi_che_iniziano_con_underscore(self) -> None:
        """`__systemRef` è una chiave di Grafana, non nostra."""
        db = sample_dashboard()
        db["panels"][1]["fieldConfig"] = {
            "defaults": {},
            "overrides": [{"properties": [{"id": "__systemRef", "value": "hideSeriesFrom"}]}],
        }
        schema.strip_internal(db)
        self.assertIn("fieldConfig", db["panels"][1])
        self.assertEqual(
            db["panels"][1]["fieldConfig"]["overrides"][0]["properties"][0]["id"],
            "__systemRef",
        )

    def test_rimuove_gli_extra_della_dashboard(self) -> None:
        db = {"panels": [], "_extras": {"cursorSync": "Off"}}
        schema.strip_internal(db)
        self.assertNotIn("_extras", db)


if __name__ == "__main__":
    unittest.main()
