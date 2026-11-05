"""Test di `grafana_tool.objects`: livello comune a righe e pannelli."""
from __future__ import annotations

import unittest

from grafana_tool import objects
from grafana_tool.model import find_row
from tests.support import panel, sample_dashboard


class SelectTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sample_dashboard()

    def test_tutte_le_righe_nell_ordine_della_dashboard(self):
        ids = [t.id for t in objects.select_targets(self.db, objects.ROW)]
        self.assertEqual(ids, [1, 5, 9])

    def test_tutti_i_pannelli_righe_escluse(self):
        ids = sorted(t.id for t in objects.select_targets(self.db, objects.PANEL))
        self.assertEqual(ids, [2, 3, 6, 7, 100])

    def test_selezione_per_id(self):
        [target] = objects.select_targets(self.db, objects.ROW, ids=[5])
        self.assertEqual(target.title, "Row B")
        self.assertEqual(target.kind, objects.ROW)

    def test_id_ripetuti_non_duplicano(self):
        self.assertEqual(len(objects.select_targets(self.db, objects.ROW, ids=[1, 1])), 1)

    def test_match_title_case_insensitive(self):
        [target] = objects.select_targets(self.db, objects.ROW, match_title="row a")
        self.assertEqual(target.id, 1)

    def test_match_type(self):
        ids = sorted(t.id for t in objects.select_targets(self.db, objects.PANEL,
                                                          match_type="TIMESERIES"))
        self.assertEqual(ids, [2, 3, 6, 7])

    def test_in_row(self):
        ids = sorted(t.id for t in objects.select_targets(self.db, objects.PANEL, in_row=5))
        self.assertEqual(ids, [6, 7])

    def test_parent_della_riga_espansa(self):
        [target] = objects.select_targets(self.db, objects.PANEL, ids=[6])
        self.assertEqual(target.parent["id"], 5)

    def test_pannello_fuori_riga_non_ha_parent(self):
        [target] = objects.select_targets(self.db, objects.PANEL, ids=[100])
        self.assertIsNone(target.parent)

    def test_id_inesistente(self):
        with self.assertRaises(ValueError) as ctx:
            objects.select_targets(self.db, objects.ROW, ids=[999])
        self.assertIn("Nessuna riga con id 999", str(ctx.exception))

    def test_id_di_una_riga_usato_sui_pannelli(self):
        with self.assertRaises(ValueError) as ctx:
            objects.select_targets(self.db, objects.PANEL, ids=[1])
        self.assertIn("usare il tipo `row`", str(ctx.exception))

    def test_in_row_vale_solo_per_i_pannelli(self):
        with self.assertRaises(ValueError) as ctx:
            objects.select_targets(self.db, objects.ROW, in_row=5)
        self.assertIn("--in-row", str(ctx.exception))

    def test_match_type_vale_solo_per_i_pannelli(self):
        with self.assertRaises(ValueError) as ctx:
            objects.select_targets(self.db, objects.ROW, match_type="row")
        self.assertIn("--match-type", str(ctx.exception))

    def test_require_selector_elenca_solo_i_selettori_validi(self):
        with self.assertRaises(ValueError) as ctx:
            objects.require_selector(objects.ROW)
        message = str(ctx.exception)
        self.assertIn("--id", message)
        self.assertNotIn("--in-row", message)
        objects.require_selector(objects.ROW, ids=[1])


class ContentTest(unittest.TestCase):
    def test_pannelli_di_una_riga(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 5)
        self.assertEqual([p["id"] for p in objects.content_panels(db, target)], [6, 7])

    def test_un_pannello_e_solo_se_stesso(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.PANEL, 2)
        self.assertEqual([p["id"] for p in objects.content_panels(db, target)], [2])

    def test_pannelli_annidati_di_un_pannello(self):
        db = {"panels": [panel(1, "gruppo", typ="rowGroup", panels=[panel(2, "a")])]}
        target = objects.find_target(db, objects.PANEL, 1)
        self.assertEqual([p["id"] for p in objects.content_panels(db, target)], [1, 2])

    def test_le_righe_non_entrano_nel_contenuto(self):
        db = {"panels": [panel(1, "gruppo", typ="group", panels=[])]}
        db["panels"].append({"id": 9, "type": "row", "title": "R", "panels": [panel(2, "a")]})
        target = objects.find_target(db, objects.ROW, 9)
        self.assertEqual([p["id"] for p in objects.content_panels(db, target)], [2])


class RemoveTest(unittest.TestCase):
    def test_rimuove_un_pannello(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.PANEL, 2)
        self.assertEqual(objects.remove(db, target), 1)
        self.assertEqual([po["id"] for po in find_row(db, 1)["panels"]], [3])
        self.assertNotIn(2, [t.id for t in objects.select_targets(db, objects.PANEL)])

    def test_rimuove_riga_espansa_con_i_fratelli(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 5)
        self.assertEqual(objects.remove(db, target), 2)
        self.assertEqual([p["id"] for p in db["panels"]], [100, 1, 9])

    def test_rimuove_riga_collassata_con_i_figli(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 1)
        self.assertEqual(objects.remove(db, target), 2)
        self.assertEqual([p["id"] for p in db["panels"]], [100, 5, 6, 7, 9])

    def test_keep_children_promuove_i_figli(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 1)
        self.assertEqual(objects.remove(db, target, keep_children=True), 0)
        self.assertEqual([p["id"] for p in db["panels"]], [100, 2, 3, 5, 6, 7, 9])

    def test_keep_children_su_riga_espansa(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 5)
        objects.remove(db, target, keep_children=True)
        self.assertEqual([p["id"] for p in db["panels"]], [100, 1, 6, 7, 9])


class MoveTest(unittest.TestCase):
    def test_pannello_in_un_altra_riga(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.PANEL, 6)
        objects.move_panel(db, target, 1)
        self.assertEqual([p["id"] for p in find_row(db, 1)["panels"]], [2, 3, 6])

    def test_pannello_in_cima_a_una_riga_espansa(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.PANEL, 2)
        objects.move_panel(db, target, 5, position="top")
        self.assertEqual([p["id"] for p in db["panels"]], [100, 1, 5, 2, 6, 7, 9])

    def test_pannello_gia_nella_riga(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.PANEL, 6)
        with self.assertRaises(ValueError) as ctx:
            objects.move_panel(db, target, 5)
        self.assertIn("già nella riga", str(ctx.exception))

    def test_riga_in_cima(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 9)
        objects.move_row(db, target, position="top")
        self.assertEqual([p.get("id") for p in db["panels"]], [9, 100, 1, 5, 6, 7])

    def test_riga_dopo_un_altra(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 9)
        objects.move_row(db, target, after=1)
        # i figli di Row A sono annidati: il blocco finisce subito dopo la riga
        self.assertEqual([p.get("id") for p in db["panels"]], [100, 1, 9, 5, 6, 7])

    def test_riga_prima_di_un_altra(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 9)
        objects.move_row(db, target, before=1)
        self.assertEqual([p.get("id") for p in db["panels"]], [100, 9, 1, 5, 6, 7])

    def test_riga_rispetto_a_se_stessa(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 5)
        with self.assertRaises(ValueError):
            objects.move_row(db, target, before=5)


class SetterTest(unittest.TestCase):
    def test_titolo_normalizzato(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 1)
        self.assertEqual(objects.set_title(db, target, "  Nuovo  "), "Nuovo")
        self.assertEqual(find_row(db, 1)["title"], "Nuovo")

    def test_titolo_vuoto(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 1)
        with self.assertRaises(ValueError):
            objects.set_title(db, target, "   ")

    def test_dedupe_titolo(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 1)
        self.assertEqual(objects.set_title(db, target, "Row B", dedupe=True), "Row B (2)")

    def test_collassa_riga_espansa(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 5)
        objects.set_collapsed(db, target, True)
        self.assertEqual([p["id"] for p in db["panels"]], [100, 1, 5, 9])
        self.assertEqual([p["id"] for p in find_row(db, 5)["panels"]], [6, 7])

    def test_espande_riga_collassata(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.ROW, 1)
        objects.set_collapsed(db, target, False)
        self.assertEqual([p["id"] for p in db["panels"]], [100, 1, 2, 3, 5, 6, 7, 9])

    def test_espansione_sposta_i_fratelli_successivi(self):
        """Una riga espansa occupa anche lo spazio dei figli.

        Le coordinate dentro una riga collassata sono relative alla riga: se
        non venissero riportate sotto l'intestazione, i figli finirebbero
        sopra le righe successive.
        """
        db = {
            "title": "Griglia",
            "panels": [
                {
                    "id": 1, "type": "row", "title": "Sopra", "collapsed": True,
                    "gridPos": {"x": 0, "y": 0, "w": 24, "h": 1},
                    "panels": [
                        {"id": 2, "type": "text", "gridPos": {"x": 0, "y": 0, "w": 12, "h": 4}},
                        {"id": 3, "type": "text", "gridPos": {"x": 12, "y": 0, "w": 12, "h": 6}},
                    ],
                },
                {
                    "id": 4, "type": "row", "title": "Sotto", "collapsed": True,
                    "gridPos": {"x": 0, "y": 1, "w": 24, "h": 1}, "panels": [],
                },
            ],
        }
        objects.set_collapsed(
            db, objects.find_target(db, objects.ROW, 1), False
        )
        figli = db["panels"][1:3]
        self.assertEqual([c["gridPos"]["y"] for c in figli], [1, 1])
        self.assertEqual(find_row(db, 4)["gridPos"]["y"], 7)

    def test_collassamento_richiude_il_blocco(self):
        db = {
            "title": "Griglia",
            "panels": [
                {
                    "id": 1, "type": "row", "title": "Sopra", "collapsed": True,
                    "gridPos": {"x": 0, "y": 0, "w": 24, "h": 1},
                    "panels": [
                        {"id": 2, "type": "text", "gridPos": {"x": 0, "y": 0, "w": 12, "h": 4}},
                    ],
                },
                {
                    "id": 4, "type": "row", "title": "Sotto", "collapsed": True,
                    "gridPos": {"x": 0, "y": 1, "w": 24, "h": 1}, "panels": [],
                },
            ],
        }
        row = objects.find_target(db, objects.ROW, 1)
        objects.set_collapsed(db, row, False)
        objects.set_collapsed(db, objects.find_target(db, objects.ROW, 1), True)
        self.assertEqual([p["id"] for p in db["panels"]], [1, 4])
        self.assertEqual([p["id"] for p in find_row(db, 1)["panels"]], [2])
        self.assertEqual(find_row(db, 4)["gridPos"]["y"], 1)

    def test_collapsed_vale_solo_per_le_righe(self):
        db = sample_dashboard()
        target = objects.find_target(db, objects.PANEL, 2)
        with self.assertRaises(ValueError):
            objects.set_collapsed(db, target, True)


if __name__ == "__main__":
    unittest.main()
