"""Test di `grafana_tool.model`: traversal, righe espanse e helper di blocco."""
from __future__ import annotations

import unittest

from grafana_tool.model import (
    append_to_row_block,
    collect_scope,
    expanded_row_siblings,
    find_panel_container,
    find_panel_parent_row,
    find_row,
    find_row_by_title,
    find_row_container,
    find_row_container_by_title,
    get_max_id,
    insert_row_after_block,
    iter_all_panels,
    iter_content_panels,
    iter_panels,
    iter_panels_with_parent,
    iter_rows,
    iter_rows_with_children,
    max_y,
    min_grid_y,
    remove_row_block,
    renumber_ids,
    row_children,
    shift_grid_y,
)
from tests.support import legacy_dashboard, panel, row, sample_dashboard

IDS = lambda items: sorted(p["id"] for p in items)  # noqa: E731


class IterTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sample_dashboard()

    def test_iter_panels_ricorsivo(self):
        nested = [panel(1, "a", panels=[panel(2, "b")])]
        self.assertEqual(IDS(iter_panels(nested)), [1, 2])

    def test_iter_panels_ignora_elementi_non_dict(self):
        self.assertEqual(list(iter_panels(["x", None, panel(1, "a")]))[0]["id"], 1)

    def test_iter_rows_schema_moderno(self):
        self.assertEqual([r["id"] for r in iter_rows(self.db)], [1, 5, 9])

    def test_iter_rows_schema_legacy(self):
        self.assertEqual([r["id"] for r in iter_rows(legacy_dashboard())], [1])

    def test_iter_rows_senza_duplicati_quando_la_riga_e_in_entrambe_le_liste(self):
        r = row(1, "R", panels=[])
        db = {"panels": [r], "rows": [r]}
        self.assertEqual(len(list(iter_rows(db))), 1)

    def test_iter_rows_non_legge_pannelli_di_contenuto_come_righe(self):
        db = {"panels": [panel(1, "a"), {"id": 2, "type": "table"}]}
        self.assertEqual(list(iter_rows(db)), [])

    def test_iter_all_panels_include_le_righe(self):
        self.assertEqual(IDS(iter_all_panels(self.db)), [1, 2, 3, 5, 6, 7, 9, 100])

    def test_iter_content_panels_esclude_le_righe(self):
        self.assertEqual(IDS(iter_content_panels(self.db)), [2, 3, 6, 7, 100])


class ExpandedRowTest(unittest.TestCase):
    """Una riga `collapsed: false` possiede i pannelli top-level che la seguono."""

    def setUp(self) -> None:
        self.db = sample_dashboard()

    def test_expanded_row_siblings(self):
        self.assertEqual(IDS(expanded_row_siblings(self.db, find_row(self.db, 5))), [6, 7])

    def test_expanded_row_siblings_si_ferma_alla_riga_successiva(self):
        self.assertEqual(
            IDS(expanded_row_siblings(self.db, find_row(self.db, 5))),
            [6, 7],
        )
        # la riga 9 chiude il blocco della riga 5
        self.assertEqual(expanded_row_siblings(self.db, find_row(self.db, 9)), [])

    def test_row_children_riga_collassata(self):
        self.assertEqual(IDS(row_children(self.db, find_row(self.db, 1))), [2, 3])

    def test_row_children_riga_espansa(self):
        self.assertEqual(IDS(row_children(self.db, find_row(self.db, 5))), [6, 7])

    def test_row_children_riga_vuota(self):
        self.assertEqual(row_children(self.db, find_row(self.db, 9)), [])

    def test_row_children_non_dict(self):
        self.assertEqual(row_children(self.db, "x"), [])

    def test_iter_rows_with_children(self):
        pairs = {r["id"]: IDS(c) for r, c in iter_rows_with_children(self.db)}
        self.assertEqual(pairs, {1: [2, 3], 5: [6, 7], 9: []})

    def test_iter_panels_with_parent_attribuisce_i_fratelli_alla_riga(self):
        owner = {p["id"]: (r["id"] if r else None) for r, p in iter_panels_with_parent(self.db)}
        self.assertEqual(
            owner,
            {100: None, 2: 1, 3: 1, 6: 5, 7: 5},
        )

    def test_iter_panels_with_parent_legacy(self):
        db = legacy_dashboard()
        pairs = list(iter_panels_with_parent(db))
        self.assertEqual([(r["id"], p["id"]) for r, p in pairs], [(1, 2)])

    def test_find_panel_parent_row(self):
        self.assertEqual(find_panel_parent_row(self.db, 2)["id"], 1)
        self.assertEqual(find_panel_parent_row(self.db, 6)["id"], 5)
        self.assertIsNone(find_panel_parent_row(self.db, 100))


class FindTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sample_dashboard()

    def test_find_row(self):
        self.assertEqual(find_row(self.db, 5)["title"], "Row B")
        self.assertIsNone(find_row(self.db, 999))

    def test_find_row_container(self):
        container, idx = find_row_container(self.db, 5)
        self.assertIs(container, self.db["panels"])
        self.assertEqual(idx, 2)
        self.assertEqual(find_row_container(self.db, 999), (None, -1))

    def test_find_panel_container_top_level(self):
        container, idx = find_panel_container(self.db, 100)
        self.assertIs(container, self.db["panels"])
        self.assertEqual(idx, 0)

    def test_find_panel_container_annidato(self):
        container, idx = find_panel_container(self.db, 3)
        self.assertIs(container, self.db["panels"][1]["panels"])
        self.assertEqual(idx, 1)

    def test_find_panel_container_inesistente(self):
        self.assertEqual(find_panel_container(self.db, 999), (None, -1))

    def test_find_row_by_title_case_insensitive(self):
        self.assertEqual(find_row_by_title(self.db, "row b")["id"], 5)

    def test_find_row_container_by_title_ritorna_tre_valori(self):
        container, idx, r = find_row_container_by_title(self.db, "Row A")
        self.assertEqual((container is self.db["panels"], idx, r["id"]), (True, 1, 1))
        self.assertEqual(find_row_container_by_title(self.db, "assente"), (None, -1, None))

    def test_get_max_id(self):
        self.assertEqual(get_max_id(self.db), 100)
        self.assertEqual(get_max_id({}), 0)


class ScopeTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sample_dashboard()

    def test_collect_scope_intera_dashboard(self):
        self.assertEqual(IDS(collect_scope(self.db, None)), [2, 3, 6, 7, 100])

    def test_collect_scope_riga_collassata(self):
        self.assertEqual(IDS(collect_scope(self.db, 1)), [2, 3])

    def test_collect_scope_riga_espansa(self):
        self.assertEqual(IDS(collect_scope(self.db, 5)), [6, 7])

    def test_collect_scope_riga_inesistente(self):
        with self.assertRaises(ValueError):
            collect_scope(self.db, 999)

    def test_max_y(self):
        self.db["panels"][3]["gridPos"] = {"h": 5, "y": 10}
        self.assertEqual(max_y(self.db), 15)


class RenumberTest(unittest.TestCase):
    def test_renumber_ids_su_riga_con_figli(self):
        obj = row(7, "x", panels=[panel(8, "a", panels=[panel(9, "b")])])
        self.assertEqual(renumber_ids(obj, 10), 13)
        self.assertEqual([obj["id"], obj["panels"][0]["id"], obj["panels"][0]["panels"][0]["id"]], [10, 11, 12])


class BlockTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = sample_dashboard()

    def test_insert_row_after_block_riga_espansa(self):
        new = row(200, "Nuova", collapsed=True)
        insert_row_after_block(self.db, 5, new)
        titles = [p.get("title") for p in self.db["panels"]]
        # la nuova riga va dopo i fratelli 6 e 7, non subito dopo la riga 5
        self.assertEqual(titles[3:6], ["B1", "B2", "Nuova"])

    def test_insert_row_after_block_riga_collassata(self):
        new = row(200, "Nuova", collapsed=True)
        insert_row_after_block(self.db, 1, new)
        self.assertEqual(self.db["panels"][2]["id"], 200)

    def test_insert_row_after_block_riga_inesistente(self):
        with self.assertRaises(ValueError):
            insert_row_after_block(self.db, 999, row(200, "x"))

    def test_remove_row_block_rimuove_riga_e_fratelli(self):
        removed = remove_row_block(self.db, 5)
        self.assertEqual(removed, 2)
        self.assertEqual([p.get("title") for p in self.db["panels"]], ["NOTE", "Row A", "Row Empty"])

    def test_remove_row_block_riga_collassata(self):
        remove_row_block(self.db, 1)
        self.assertIsNone(find_row(self.db, 1))
        self.assertEqual([p.get("title") for p in self.db["panels"]], ["NOTE", "Row B", "B1", "B2", "Row Empty"])

    def test_remove_row_block_inesistente(self):
        with self.assertRaises(ValueError):
            remove_row_block(self.db, 999)

    def test_append_to_row_block_riga_collassata(self):
        append_to_row_block(self.db, find_row(self.db, 1), panel(50, "nuovo"))
        self.assertEqual(IDS(self.db["panels"][1]["panels"]), [2, 3, 50])

    def test_append_to_row_block_riga_espansa(self):
        append_to_row_block(self.db, find_row(self.db, 5), panel(50, "nuovo"))
        titles = [p.get("title") for p in self.db["panels"]]
        self.assertEqual(titles[3:6], ["B1", "B2", "nuovo"])
        self.assertEqual(self.db["panels"][2]["panels"], [])


class GridTest(unittest.TestCase):
    def test_min_grid_y(self):
        panels = [panel(1), panel(2)]
        panels[0]["gridPos"]["y"] = 4
        panels[1]["gridPos"]["y"] = 9
        self.assertEqual(min_grid_y(panels), 4)
        self.assertEqual(min_grid_y([]), 0)
        self.assertEqual(min_grid_y({}), 0)

    def test_shift_grid_y_include_annidati(self):
        panels = [panel(1, panels=[panel(2)])]
        panels[0]["gridPos"]["y"] = 5
        panels[0]["panels"][0]["gridPos"]["y"] = 5
        shift_grid_y(panels, -5)
        self.assertEqual(panels[0]["gridPos"]["y"], 0)
        self.assertEqual(panels[0]["panels"][0]["gridPos"]["y"], 0)

    def test_shift_grid_y_zero_non_fa_nulla(self):
        p = panel(1)
        p["gridPos"]["y"] = 3
        shift_grid_y([p], 0)
        self.assertEqual(p["gridPos"]["y"], 3)


if __name__ == "__main__":
    unittest.main()
