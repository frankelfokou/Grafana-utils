"""Test del tipo `tab`: selezione, CRUD, estrazione e guardie.

I tab sono il terzo tipo di oggetto della CLI. Vivono nei metadati interni
(`_tabs`, `row["_tab"]`) e i comandi li trattano come righe e pannelli:
stessi verbi, stessi selettori, stesse regole di rifiuto.
"""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from grafana_tool import model, objects, schema, tabs

from tests.support import CLITestCase, sample_dashboard

FIXTURES = Path(__file__).resolve().parent / "fixtures"
V2_FIXTURE = FIXTURES / "dashboard-v2.json"


def v2_fixture() -> dict:
    return json.loads(V2_FIXTURE.read_text(encoding="utf-8"))


def canonical() -> dict:
    from grafana_tool import formats

    return formats.load(v2_fixture()).db


class TabModelTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = canonical()

    def test_tab_della_dashboard_v2(self) -> None:
        self.assertEqual(
            [t["title"] for t in tabs.all_tabs(self.db)],
            ["Applicativa", "Sistemistica"],
        )

    def test_righe_per_tab(self) -> None:
        self.assertEqual([r["title"] for r in tabs.rows_of(self.db, 1)], ["Generale"])
        self.assertEqual([r["title"] for r in tabs.rows_of(self.db, 2)], ["Infra"])

    def test_pannelli_per_tab(self) -> None:
        self.assertEqual(
            [p["title"] for p in tabs.panels_of(self.db, 1)], ["Traffico", "Note"]
        )
        self.assertEqual([p["title"] for p in tabs.panels_of(self.db, 2)], ["Nodi attivi"])

    def test_pannelli_fuori_riga_sono_del_primo_tab(self) -> None:
        db = canonical()
        db["panels"].append({"id": 99, "type": "text", "title": "Fuori", "gridPos": {}})
        self.assertIn(99, [p["id"] for p in tabs.panels_of(db, 1)])
        self.assertNotIn(99, [p["id"] for p in tabs.panels_of(db, 2)])

    def test_requisiti_e_messaggio(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            tabs.require(self.db, 42)
        self.assertIn("Tab 42 non trovato", str(ctx.exception))
        self.assertIn("Applicativa", str(ctx.exception))

    def test_prossimo_id(self) -> None:
        self.assertEqual(tabs.next_id(self.db), 3)

    def test_una_dashboard_classica_ha_un_tab(self) -> None:
        db = sample_dashboard()
        schema.ensure_tabs(db)
        self.assertEqual(len(tabs.all_tabs(db)), 1)


class TabSelectionTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = canonical()

    def test_per_id(self) -> None:
        target = objects.select_targets(self.db, objects.TAB, ids=[2])[0]
        self.assertEqual(target.title, "Sistemistica")
        self.assertEqual(target.kind, objects.TAB)

    def test_per_titolo_case_insensitive(self) -> None:
        targets = objects.select_targets(self.db, objects.TAB, match_title="applic")
        self.assertEqual([t.id for t in targets], [1])

    def test_match_type_rifiutato(self) -> None:
        with self.assertRaises(ValueError):
            objects.select_targets(self.db, objects.TAB, match_type="timeseries")

    def test_in_tab_rifiutato(self) -> None:
        with self.assertRaises(ValueError) as ctx:
            objects.select_targets(self.db, objects.TAB, in_tab=1)
        self.assertIn("--in-tab", str(ctx.exception))

    def test_in_tab_filtra_le_righe(self) -> None:
        rows = objects.select_targets(self.db, objects.ROW, in_tab=2)
        self.assertEqual([t.title for t in rows], ["Infra"])

    def test_in_tab_filtra_i_pannelli(self) -> None:
        panels = objects.select_targets(self.db, objects.PANEL, in_tab=1)
        self.assertEqual(sorted(t.title for t in panels), ["Note", "Traffico"])

    def test_contenuto_di_un_tab(self) -> None:
        target = objects.select_targets(self.db, objects.TAB, ids=[1])[0]
        self.assertEqual(
            [p["title"] for p in objects.content_panels(self.db, target)],
            ["Traffico", "Note"],
        )


class TabOperationsTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = canonical()

    def test_rinomina(self) -> None:
        target = objects.select_targets(self.db, objects.TAB, ids=[1])[0]
        objects.set_title(self.db, target, "Nuovo nome")
        self.assertEqual(tabs.find(self.db, 1)["title"], "Nuovo nome")

    def test_sposta_in_cima(self) -> None:
        target = objects.select_targets(self.db, objects.TAB, ids=[2])[0]
        objects.move_tab(self.db, target, position="top")
        self.assertEqual([t["title"] for t in tabs.all_tabs(self.db)],
                         ["Sistemistica", "Applicativa"])

    def test_sposta_dopo_un_altro(self) -> None:
        target = objects.select_targets(self.db, objects.TAB, ids=[1])[0]
        objects.move_tab(self.db, target, after=2)
        self.assertEqual([t["id"] for t in tabs.all_tabs(self.db)], [2, 1])

    def test_sposta_rispetto_a_se_stesso(self) -> None:
        target = objects.select_targets(self.db, objects.TAB, ids=[1])[0]
        with self.assertRaises(ValueError):
            objects.move_tab(self.db, target, before=1)

    def test_elimina_con_contenuto(self) -> None:
        target = objects.select_targets(self.db, objects.TAB, ids=[1])[0]
        removed = objects.remove(self.db, target)
        self.assertEqual(removed, 2)  # i due pannelli di "Generale"
        self.assertEqual([t["id"] for t in tabs.all_tabs(self.db)], [2])
        self.assertEqual([p["id"] for _, _, p, _ in model.iter_panel_slots(self.db)], [3])

    def test_elimina_conservando_le_righe(self) -> None:
        target = objects.select_targets(self.db, objects.TAB, ids=[1])[0]
        removed = objects.remove(self.db, target, keep_children=True)
        self.assertEqual(removed, 0)
        self.assertEqual([t["id"] for t in tabs.all_tabs(self.db)], [2])
        self.assertEqual(schema.tab_of(model.find_row(self.db, 4)), 2)
        self.assertEqual(len(list(model.iter_all_panels(self.db))), 5)

    def test_ultimo_tab_non_si_elimina(self) -> None:
        target = objects.select_targets(self.db, objects.TAB, ids=[2])[0]
        objects.remove(self.db, target)
        last = objects.select_targets(self.db, objects.TAB, ids=[1])[0]
        with self.assertRaises(ValueError) as ctx:
            objects.remove(self.db, last)
        self.assertIn("ultimo tab", str(ctx.exception))

    def test_assegna_una_riga_a_un_tab(self) -> None:
        target = objects.select_targets(self.db, objects.ROW, ids=[4])[0]
        objects.set_tab(self.db, target, 2)
        self.assertEqual(schema.tab_of(model.find_row(self.db, 4)), 2)


class TabCLITest(CLITestCase):
    def _src(self) -> str:
        return self.write_json("in.json", v2_fixture())

    def test_list(self) -> None:
        code, out, _ = self.run_cli("list", "tab", self._src())
        self.assertEqual(code, 0)
        self.assertIn("Applicativa", out)
        self.assertIn("Sistemistica", out)
        self.assertIn("2", out)  # conteggio righe del primo tab

    def test_list_json(self) -> None:
        code, out, _ = self.run_cli("list", "tab", self._src(), "--format", "json")
        self.assertEqual(code, 0)
        payload = json.loads(out)
        self.assertEqual([t["id"] for t in payload], [1, 2])
        self.assertEqual(payload[0]["panel_count"], 2)
        self.assertEqual(payload[1]["row_count"], 1)

    def test_create(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "create", "tab", "--title", "Terzo", self._src(), "-o", out
        )
        self.assertEqual(code, 0, stdout)
        scritto = self.read_json(out)
        self.assertEqual(
            [t["spec"]["title"] for t in scritto["layout"]["spec"]["tabs"]],
            ["Applicativa", "Sistemistica", "Terzo"],
        )

    def test_create_in_cima(self) -> None:
        out = self.tmp / "out.json"
        self.run_cli("create", "tab", "--title", "Primo", "--position", "top",
                     self._src(), "-o", out)
        scritto = self.read_json(out)
        self.assertEqual(scritto["layout"]["spec"]["tabs"][0]["spec"]["title"], "Primo")

    def test_create_senza_titolo(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("create", "tab", self._src(), "-o", out)
        self.assertEqual(code, 0, stdout)
        self.assertIn("Tab 3", stdout)

    def test_create_da_template_rifiutato(self) -> None:
        code, _, err = self.run_cli(
            "create", "tab", "--template", "x.json", self._src(),
            "-o", self.tmp / "out.json",
        )
        self.assertEqual(code, 1)
        self.assertIn("non si copia", err)

    def test_update_rinomina(self) -> None:
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli(
            "update", "tab", "--id", "2", "--title", "Sistemistica",
            self._src(), "-o", out,
        )
        self.assertEqual(code, 0)
        scritto = self.read_json(out)
        self.assertEqual(scritto["layout"]["spec"]["tabs"][1]["spec"]["title"],
                         "Sistemistica")

    def test_update_datasource_su_tutto_il_tab(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "update", "tab", "--id", "1", "--datasource", "nuovo",
            self._src(), "-o", out,
        )
        self.assertEqual(code, 0, stdout)
        scritto = self.read_json(out)
        for name in ("panel-1", "panel-2"):
            for query in scritto["elements"][name]["spec"]["data"]["spec"]["queries"]:
                self.assertEqual(query["spec"]["query"]["datasource"]["name"], "nuovo")

    def test_delete(self) -> None:
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("delete", "tab", "--id", "1", self._src(), "-o", out)
        self.assertEqual(code, 0)
        scritto = self.read_json(out)
        self.assertEqual([t["spec"]["title"] for t in scritto["layout"]["spec"]["tabs"]],
                         ["Sistemistica"])
        self.assertNotIn("panel-1", scritto["elements"])

    def test_delete_conservando_le_righe(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "delete", "tab", "--id", "1", "--keep-children", self._src(), "-o", out
        )
        self.assertEqual(code, 0, stdout)
        scritto = self.read_json(out)
        righe = scritto["layout"]["spec"]["tabs"][0]["spec"]["layout"]["spec"]["rows"]
        self.assertEqual([r["spec"]["title"] for r in righe], ["Generale", "Infra"])

    def test_delete_ultimo_tab_rifiutato(self) -> None:
        raw = v2_fixture()
        raw["layout"]["spec"]["tabs"] = raw["layout"]["spec"]["tabs"][:1]
        src = self.write_json("uno.json", raw)
        out = self.tmp / "out.json"
        code, _, err = self.run_cli("delete", "tab", "--id", "1", src, "-o", out)
        self.assertEqual(code, 1)
        self.assertIn("ultimo tab", err)
        self.assertFalse(out.exists())

    def test_move_tab(self) -> None:
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli(
            "move", "tab", "--id", "2", "--position", "top", self._src(), "-o", out
        )
        self.assertEqual(code, 0)
        scritto = self.read_json(out)
        self.assertEqual(
            [t["spec"]["title"] for t in scritto["layout"]["spec"]["tabs"]],
            ["Sistemistica", "Applicativa"],
        )

    def test_move_tab_con_to_row_rifiutato(self) -> None:
        code, _, err = self.run_cli(
            "move", "tab", "--id", "2", "--to-row", "4", self._src(),
            "-o", self.tmp / "out.json",
        )
        self.assertEqual(code, 1)
        self.assertIn("--to-row vale solo per i pannelli", err)

    def test_create_row_in_un_tab(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "create", "row", "--from-id", "4", "--title", "Ancora",
            "--to-tab", "2", self._src(), "-o", out,
        )
        self.assertEqual(code, 0, stdout)
        scritto = self.read_json(out)
        righe = scritto["layout"]["spec"]["tabs"][1]["spec"]["layout"]["spec"]["rows"]
        self.assertEqual(righe[-1]["spec"]["title"], "Ancora")

    def test_move_row_in_un_tab(self) -> None:
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli(
            "move", "row", "--id", "4", "--to-tab", "2", self._src(), "-o", out
        )
        self.assertEqual(code, 0)
        scritto = self.read_json(out)
        righe = scritto["layout"]["spec"]["tabs"][1]["spec"]["layout"]["spec"]["rows"]
        self.assertEqual([r["spec"]["title"] for r in righe], ["Infra", "Generale"])

    def test_create_panel_con_to_tab_rifiutato(self) -> None:
        code, _, err = self.run_cli(
            "create", "panel", "--from-id", "1", "--to-tab", "2", self._src(),
            "-o", self.tmp / "out.json",
        )
        self.assertEqual(code, 1)
        self.assertIn("un pannello segue la riga", err)

    def test_extract_tab(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "extract", "tab", "--id", "2", self._src(), "-o", out,
            "--to-format", "v2",
        )
        self.assertEqual(code, 0, stdout)
        scritto = self.read_json(out)
        self.assertEqual([t["spec"]["title"] for t in scritto["layout"]["spec"]["tabs"]],
                         ["Sistemistica"])
        self.assertEqual(list(scritto["elements"]), ["panel-3"])

    def test_extract_tab_classico_ha_una_sola_riga_per_tab(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "extract", "tab", "--id", "1", self._src(), "-o", out,
            "--to-format", "classic",
        )
        self.assertEqual(code, 0, stdout)
        scritto = self.read_json(out)
        self.assertEqual([p["type"] for p in scritto["panels"] if p.get("type") == "row"],
                         ["row"])


if __name__ == "__main__":
    unittest.main()
