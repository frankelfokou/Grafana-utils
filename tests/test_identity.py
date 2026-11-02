"""Test di `grafana_tool.identity`: uid, titoli e id di pannello."""
from __future__ import annotations

import unittest

from grafana_tool.identity import (
    UID_ALPHABET,
    all_titles,
    dedupe_panel_titles,
    id_range_collisions,
    new_uid,
    new_uid_not_in,
    parse_inventory,
    seal_new_dashboard,
    unique_title,
)
from tests.support import panel, row, sample_dashboard


class UidTest(unittest.TestCase):
    def test_lunghezza_e_alfabeto(self):
        uid = new_uid()
        self.assertEqual(len(uid), 9)
        self.assertTrue(set(uid) <= set(UID_ALPHABET))

    def test_lunghezza_personalizzata(self):
        self.assertEqual(len(new_uid(5)), 5)

    def test_lunghezza_non_valida(self):
        with self.assertRaises(ValueError):
            new_uid(0)

    def test_uid_generati_distinti(self):
        self.assertEqual(len({new_uid() for _ in range(20)}), 20)

    def test_new_uid_not_in_evita_i_valori_noti(self):
        taken = {new_uid() for _ in range(50)}
        uid = new_uid_not_in(taken)
        self.assertNotIn(uid.casefold(), {t.casefold() for t in taken})


class UniqueTitleTest(unittest.TestCase):
    def test_titolo_libero_resta_invariato(self):
        self.assertEqual(unique_title("CPU", ["MEM"]), "CPU")

    def test_titolo_occupato_riceve_suffisso(self):
        self.assertEqual(unique_title("CPU", ["CPU"]), "CPU (2)")
        self.assertEqual(unique_title("CPU", ["CPU", "CPU (2)"]), "CPU (3)")

    def test_confronto_case_insensitive_e_spazi(self):
        self.assertEqual(unique_title("cpu", ["  CPU  "]), "cpu (2)")

    def test_titolo_vuoto_diventa_senza_titolo(self):
        self.assertEqual(unique_title("", []), "Senza titolo")


class DedupePanelTitlesTest(unittest.TestCase):
    def test_rinomina_solo_i_duplicati(self):
        panels = [panel(1, "CPU"), panel(2, "MEM"), panel(3, "CPU")]
        renamed = dedupe_panel_titles(panels, ["CPU"])
        self.assertEqual(renamed, 2)
        self.assertEqual([p["title"] for p in panels], ["CPU (2)", "MEM", "CPU (3)"])

    def test_scende_nei_pannelli_annidati_e_ignora_le_righe(self):
        r = row(10, "CPU", panels=[panel(11, "CPU")])
        renamed = dedupe_panel_titles([r], ["CPU"])
        self.assertEqual(renamed, 1)
        self.assertEqual(r["title"], "CPU")  # le righe non vengono toccate
        self.assertEqual(r["panels"][0]["title"], "CPU (2)")

    def test_pannelli_senza_titolo_restano_senza(self):
        p = panel(1)
        self.assertEqual(dedupe_panel_titles([p], []), 0)
        self.assertNotIn("title", p)


class InventoryTest(unittest.TestCase):
    def test_lista_di_dashboard(self):
        uids, titles = parse_inventory([{"uid": "a", "title": "A"}, {"uid": "b"}])
        self.assertEqual(uids, {"a", "b"})
        self.assertEqual(titles, {"A"})

    def test_formato_dashboards(self):
        uids, titles = parse_inventory({"dashboards": [{"uid": "a", "title": "A"}]})
        self.assertEqual((uids, titles), ({"a"}, {"A"}))

    def test_singola_dashboard(self):
        uids, titles = parse_inventory({"uid": "a", "title": "A"})
        self.assertEqual((uids, titles), ({"a"}, {"A"}))

    def test_radice_non_valida(self):
        with self.assertRaises(ValueError):
            parse_inventory("nope")

    def test_elementi_non_oggetto_vengono_ignorati(self):
        self.assertEqual(parse_inventory([1, None, {"uid": "a"}]), ({"a"}, set()))


class SealNewDashboardTest(unittest.TestCase):
    def test_identita_generata(self):
        db = {"title": "Vecchia", "id": 42, "version": 7, "panels": []}
        ident = seal_new_dashboard(db, taken_uids={"abc"}, taken_titles={"Nuova"})
        self.assertEqual(len(ident.uid), 9)
        self.assertNotEqual(ident.uid, "abc")
        self.assertEqual(db["uid"], ident.uid)
        self.assertIsNone(db["id"])
        self.assertEqual(db["version"], 1)
        self.assertEqual(db["title"], "Vecchia")

    def test_titolo_reso_unico(self):
        db = {"title": "Dashboard", "panels": []}
        ident = seal_new_dashboard(db, taken_titles=["Dashboard"])
        self.assertEqual(ident.title, "Dashboard (2)")
        self.assertEqual(db["title"], "Dashboard (2)")

    def test_uid_esplicito_libero(self):
        db = {"title": "X", "panels": []}
        ident = seal_new_dashboard(db, uid="nuovo-uid", taken_uids={"altro"})
        self.assertEqual(ident.uid, "nuovo-uid")

    def test_uid_esplicito_in_conflitto(self):
        db = {"title": "X", "panels": []}
        with self.assertRaises(ValueError) as ctx:
            seal_new_dashboard(db, uid="usato", taken_uids={"usato"})
        self.assertIn("già usato", str(ctx.exception))

    def test_uid_esplicito_vuoto(self):
        with self.assertRaises(ValueError):
            seal_new_dashboard({"title": "X"}, uid="  ")


class PanelIdTest(unittest.TestCase):
    def test_id_range_collisions(self):
        db = sample_dashboard()
        self.assertEqual(id_range_collisions(db, 100, 3), [100])
        self.assertEqual(id_range_collisions(db, 200, 3), [])

    def test_all_titles_include_righe_e_pannelli(self):
        titles = all_titles(sample_dashboard())
        self.assertIn("Row A", titles)
        self.assertIn("A1", titles)


if __name__ == "__main__":
    unittest.main()
