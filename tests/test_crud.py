"""Test del blocco CRUD unificato: stessi verbi per righe e pannelli.

Ogni classe copre un verbo e verifica esplicitamente entrambi i tipi, perché
la promessa dell'interfaccia è che `list`, `create`, `update`, `delete`,
`move` ed `extract` funzionino allo stesso modo su `row` e `panel`.
"""
from __future__ import annotations

import json
import unittest

from grafana_tool.model import find_row, iter_all_panels, row_children
from tests.support import CLITestCase, all_ids, panel, row, sample_dashboard


class CreateRowTest(CLITestCase):
    def test_dal_template_predefinito(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("create", "row", src, "-o", out)
        self.assertEqual(code, 0, stdout)
        nuova = self.read_json(out)["panels"][-1]
        self.assertEqual(len(nuova["panels"]), 16)
        self.assertTrue(nuova["collapsed"])
        self.assertNotIn("${", json.dumps(nuova))
        exprs = [t.get("expr", "") for p in nuova["panels"] for t in p.get("targets") or []]
        self.assertTrue(any('namespace=~"universo-on-line-feu-up"' in e for e in exprs))

    def test_dal_template_con_parametri(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("create", "row", src, "--namespace", "pa-digital",
                     "--cluster-gen", "3", "--title", "TEST", "--base-id", "500",
                     "-o", out)
        nuova = self.read_json(out)["panels"][-1]
        self.assertEqual(nuova["id"], 500)
        self.assertEqual(nuova["panels"][0]["id"], 501)
        self.assertEqual(nuova["title"], "TEST")
        exprs = [t.get("expr", "") for p in nuova["panels"] for t in p.get("targets") or []]
        self.assertTrue(any('cluster_gen="3"' in e for e in exprs))

    def test_parametri_da_file(self):
        src = self.write_json("in.json", sample_dashboard())
        params = self.write_json("p.json", {"NAMESPACE": "da-file", "ROW_TITLE": "T-file"})
        out = self.tmp / "out.json"
        self.run_cli("create", "row", src, "--params", params, "-o", out)
        nuova = self.read_json(out)["panels"][-1]
        self.assertEqual(nuova["title"], "T-file")
        self.assertIn("da-file", json.dumps(nuova))

    def test_copia_di_una_riga_espansa(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("create", "row", src, "--from-id", "5", "-o", out)
        self.assertEqual(code, 0, stdout)
        db = self.read_json(out)
        copia = find_row(db, 101)
        self.assertEqual(copia["title"], "Row B")
        self.assertTrue(copia["collapsed"])
        self.assertEqual([p["id"] for p in copia["panels"]], [102, 103])
        self.assertEqual([p["title"] for p in copia["panels"]], ["B1", "B2"])

    def test_copia_con_titolo_e_dedupe(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("create", "row", src, "--from-id", "1", "--title", "Row B",
                     "--dedupe-titles", "-o", out)
        db = self.read_json(out)
        self.assertEqual(find_row(db, 101)["title"], "Row B (2)")
        self.assertEqual([p["title"] for p in find_row(db, 101)["panels"]],
                         ["A1 (2)", "A2 (2)"])

    def test_sostituzioni_sui_figli(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("create", "row", src, "--from-id", "5", "--replace", "up=down", "-o", out)
        copia = find_row(self.read_json(out), 101)
        self.assertEqual(copia["panels"][0]["targets"][0]["expr"], 'down{panel="6"}')

    def test_posizione_in_cima(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("create", "row", src, "--from-id", "5", "--position", "top", "-o", out)
        db = self.read_json(out)
        self.assertEqual(db["panels"][0]["id"], 101)
        self.assertEqual(db["panels"][0]["gridPos"]["y"], 0)

    def test_riga_espansa(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("create", "row", src, "--from-id", "5", "--expanded", "-o", out)
        db = self.read_json(out)
        nuova = next(p for p in db["panels"] if p.get("id") == 101)
        self.assertFalse(nuova["collapsed"])
        self.assertEqual(nuova["panels"], [])
        self.assertEqual(len(row_children(db, nuova)), 2)

    def test_on_existing_di_default_e_errore(self):
        db = sample_dashboard()
        db["panels"].append(row(50, "TEST"))
        src = self.write_json("in.json", db)
        code, _, err = self.run_cli("create", "row", src, "--title", "TEST",
                                    "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("Esiste già la riga", err)

    def test_on_existing_skip(self):
        db = sample_dashboard()
        db["panels"].append(row(50, "TEST"))
        src = self.write_json("in.json", db)
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("create", "row", src, "--title", "TEST",
                                       "--on-existing", "skip", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("nessuna modifica", stdout)
        self.assertEqual(len(self.read_json(out)["panels"]), 7)

    def test_on_existing_replace(self):
        db = sample_dashboard()
        db["panels"].append(row(50, "TEST"))
        src = self.write_json("in.json", db)
        out = self.tmp / "out.json"
        self.run_cli("create", "row", src, "--title", "TEST",
                     "--on-existing", "replace", "-o", out)
        titoli = [p.get("title") for p in self.read_json(out)["panels"]]
        self.assertEqual(titoli.count("TEST"), 1)

    def test_base_id_in_conflitto(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("create", "row", src, "--base-id", "100",
                                    "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("collide", err)

    def test_template_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, _ = self.run_cli("create", "row", src,
                                  "--template", str(self.tmp / "nope.json"),
                                  "-o", self.tmp / "o.json")
        self.assertEqual(code, 2)


class CreatePanelTest(CLITestCase):
    def test_copia_accanto_all_originale(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("create", "panel", src, "--from-id", "2", "-o", out)
        self.assertEqual(code, 0, stdout)
        db = self.read_json(out)
        self.assertEqual([p["id"] for p in find_row(db, 1)["panels"]], [2, 101, 3])
        self.assertEqual(find_row(db, 1)["panels"][1]["title"], "A1")

    def test_copia_in_un_altra_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("create", "panel", src, "--from-id", "2", "--to-row", "5", "-o", out)
        db = self.read_json(out)
        self.assertEqual([p["id"] for p in row_children(db, find_row(db, 5))], [6, 7, 101])

    def test_titolo_and_replace(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("create", "panel", src, "--from-id", "2", "--title", "N",
                     "--replace", "up=down", "-o", out)
        clone = find_row(self.read_json(out), 1)["panels"][1]
        self.assertEqual(clone["title"], "N")
        self.assertEqual(clone["targets"][0]["expr"], 'down{panel="2"}')

    def test_dedupe_titles(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("create", "panel", src, "--from-id", "2", "--dedupe-titles", "-o", out)
        self.assertEqual(find_row(self.read_json(out), 1)["panels"][1]["title"], "A1 (2)")

    def test_id_unici_nel_clone_annidato(self):
        db = {"panels": [panel(1, "gruppo", typ="group", panels=[panel(2, "a")])]}
        src = self.write_json("in.json", db)
        out = self.tmp / "out.json"
        self.run_cli("create", "panel", src, "--from-id", "1", "-o", out)
        clonato = self.read_json(out)["panels"][1]
        self.assertEqual([p["id"] for p in iter_all_panels({"panels": [clonato]})], [3, 4])

    def test_senza_sorgente_e_un_errore(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("create", "panel", src, "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("Specificare la sorgente", err)

    def test_da_template_di_pannello(self):
        tpl = panel(0, "Template")
        tpl["targets"][0]["expr"] = "up{g=\"${NAMESPACE}\"}"
        src = self.write_json("in.json", sample_dashboard())
        template = self.write_json("tpl.json", tpl)
        out = self.tmp / "out.json"
        self.run_cli("create", "panel", src, "--template", template,
                     "--namespace", "ns1", "--title", "Dal template", "-o", out)
        nuovo = self.read_json(out)["panels"][-1]
        self.assertEqual(nuovo["title"], "Dal template")
        self.assertIn('g="ns1"', nuovo["targets"][0]["expr"])

    def test_riga_inesistente_come_id(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("create", "panel", src, "--from-id", "1",
                                    "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("usare il tipo `row`", err)


class UpdateTest(CLITestCase):
    def test_riga_titolo_per_id(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("update", "row", src, "--id", "1",
                                       "--title", "Row A rinnovata", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("titolo 'Row A rinnovata'", stdout)
        self.assertEqual(find_row(self.read_json(out), 1)["title"], "Row A rinnovata")
        self.assertEqual(find_row(self.read_json(src), 1)["title"], "Row A")

    def test_riga_titolo_per_match_case_insensitive(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("update", "row", src, "--match-title", "row a", "--title", "X", "-o", out)
        self.assertEqual(find_row(self.read_json(out), 1)["title"], "X")

    def test_espande_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("update", "row", src, "--id", "1", "--expanded", "-o", out)
        db = self.read_json(out)
        self.assertEqual([p["id"] for p in db["panels"]], [100, 1, 2, 3, 5, 6, 7, 9])
        self.assertEqual(len(row_children(db, find_row(db, 1))), 2)

    def test_collassa_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("update", "row", src, "--id", "5", "--collapsed", "-o", out)
        db = self.read_json(out)
        self.assertEqual([p["id"] for p in db["panels"]], [100, 1, 5, 9])
        self.assertEqual([p["id"] for p in find_row(db, 5)["panels"]], [6, 7])

    def test_dedupe_titolo(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("update", "row", src, "--id", "1", "--title", "Row B",
                     "--dedupe-titles", "-o", out)
        self.assertEqual(find_row(self.read_json(out), 1)["title"], "Row B (2)")

    def test_pannello_titolo(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("update", "panel", src, "--id", "2", "--title", "P2", "-o", out)
        self.assertEqual(find_row(self.read_json(out), 1)["panels"][0]["title"], "P2")

    def test_pannello_datasource(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("update", "panel", src, "--in-row", "1",
                                  "--datasource", "nuovo",
                                  "--datasource-type", "prometheus", "-o", out)
        self.assertEqual(code, 0)
        for p in find_row(self.read_json(out), 1)["panels"]:
            self.assertEqual(p["datasource"]["uid"], "nuovo")
            self.assertEqual(p["targets"][0]["datasource"]["uid"], "nuovo")

    def test_su_una_riga_il_contenuto_sono_i_suoi_pannelli(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("update", "row", src, "--id", "1",
                                       "--replace", "up=down", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("2 modifiche al contenuto", stdout)
        figli = find_row(self.read_json(out), 1)["panels"]
        self.assertTrue(all("down{" in p["targets"][0]["expr"] for p in figli))

    def test_replace_per_tipo(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("update", "panel", src, "--match-type", "text",
                     "--replace", "up=down", "-o", out)
        db = self.read_json(out)
        self.assertIn("down{", db["panels"][0]["targets"][0]["expr"])

    def test_datasource_create(self):
        src = self.write_json("in.json", {"panels": [{"id": 1, "type": "text", "title": "x"}]})
        out = self.tmp / "out.json"
        self.run_cli("update", "panel", src, "--id", "1", "--datasource", "u",
                     "--datasource-create", "-o", out)
        self.assertEqual(self.read_json(out)["panels"][0]["datasource"],
                         {"type": "prometheus", "uid": "u"})

    def test_senza_modifiche(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("update", "row", src, "--id", "1",
                                    "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("Nessuna modifica richiesta", err)

    def test_datasource_type_senza_datasource(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("update", "panel", src, "--id", "2",
                                    "--datasource-type", "foo", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("richiede --datasource", err)

    def test_collapsed_su_un_pannello(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("update", "panel", src, "--id", "2",
                                    "--collapsed", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("solo per le righe", err)

    def test_titolo_vuoto(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("update", "row", src, "--id", "1",
                                    "--title", "   ", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("non può essere vuoto", err)

    def test_legacy_non_supporta_expanded(self):
        src = self.write_json("in.json", {
            "title": "Legacy",
            "rows": [{"id": 1, "title": "L", "panels": [panel(2, "a")]}],
        })
        code, _, err = self.run_cli("update", "row", src, "--id", "1",
                                    "--expanded", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("legacy", err)


class DeleteTest(CLITestCase):
    def test_riga_collassata_con_i_figli(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("delete", "row", src, "--id", "1", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("con 2 pannelli", stdout)
        db = self.read_json(out)
        self.assertIsNone(find_row(db, 1))
        self.assertEqual([p["id"] for p in db["panels"]], [100, 5, 6, 7, 9])

    def test_riga_espansa_con_i_fratelli(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("delete", "row", src, "--id", "5", "-o", out)
        db = self.read_json(out)
        self.assertEqual([p["id"] for p in db["panels"]], [100, 1, 9])
        self.assertEqual(all_ids(db), [1, 2, 3, 9, 100])

    def test_keep_children(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("delete", "row", src, "--id", "1", "--keep-children", "-o", out)
        db = self.read_json(out)
        self.assertEqual([p["id"] for p in db["panels"]], [100, 2, 3, 5, 6, 7, 9])

    def test_pannello_per_id(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("delete", "panel", src, "--id", "2", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("eliminato", stdout)
        self.assertEqual([p["id"] for p in find_row(self.read_json(out), 1)["panels"]], [3])

    def test_pannelli_per_tipo(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("delete", "panel", src, "--match-type", "text", "-o", out)
        self.assertNotIn(100, all_ids(self.read_json(out)))

    def test_pannelli_per_titolo_case_insensitive(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("delete", "panel", src,
                                       "--match-title", "^b", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("eliminate/i: 2", stdout)
        db = self.read_json(out)
        self.assertEqual(row_children(db, find_row(db, 5)), [])

    def test_senza_selettore(self):
        src = self.write_json("in.json", sample_dashboard())
        for kind in ("row", "panel"):
            code, _, err = self.run_cli("delete", kind, src, "-o", self.tmp / "o.json")
            self.assertEqual(code, 1)
            self.assertIn("Specificare un selettore", err)

    def test_keep_children_su_pannello(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("delete", "panel", src, "--id", "2",
                                    "--keep-children", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("solo per le righe", err)


class MoveTest(CLITestCase):
    def test_pannello_in_un_altra_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("move", "panel", src, "--id", "6",
                                       "--to-row", "1", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("nella riga 1", stdout)
        self.assertEqual([p["id"] for p in find_row(self.read_json(out), 1)["panels"]],
                         [2, 3, 6])

    def test_tutti_i_pannelli_di_una_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("move", "panel", src, "--in-row", "5", "--to-row", "1", "-o", out)
        db = self.read_json(out)
        self.assertEqual([p["id"] for p in find_row(db, 1)["panels"]], [2, 3, 6, 7])

    def test_pannello_in_cima(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("move", "panel", src, "--id", "2", "--to-row", "9",
                     "--position", "top", "-o", out)
        self.assertEqual([p["id"] for p in find_row(self.read_json(out), 9)["panels"]], [2])

    def test_pannello_senza_destinazione(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("move", "panel", src, "--id", "2",
                                    "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("--to-row", err)

    def test_pannello_gia_nella_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("move", "panel", src, "--id", "6",
                                    "--to-row", "5", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("già nella riga", err)

    def test_riga_in_cima(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("move", "row", src, "--id", "9", "--position", "top", "-o", out)
        self.assertEqual([p["id"] for p in self.read_json(out)["panels"]],
                         [9, 100, 1, 5, 6, 7])

    def test_riga_dopo_un_altra(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("move", "row", src, "--id", "9", "--after", "1", "-o", out)
        self.assertEqual([p["id"] for p in self.read_json(out)["panels"]],
                         [100, 1, 9, 5, 6, 7])

    def test_riga_non_usa_to_row(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("move", "row", src, "--id", "9",
                                    "--to-row", "1", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("solo per i pannelli", err)

    def test_pannello_dopo_un_altro_pannello(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("move", "panel", src, "--id", "2",
                                       "--after", "3", "-o", out)
        self.assertEqual(code, 0, stdout)
        self.assertEqual([p["id"] for p in find_row(self.read_json(out), 1)["panels"]],
                         [3, 2])

    def test_destinazioni_in_conflitto(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("move", "panel", src, "--id", "2",
                                    "--to-row", "5", "--after", "3",
                                    "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("non entrambi", err)


class ExtractTest(CLITestCase):
    def test_riga_espansa_include_i_fratelli(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("extract", "row", src, "--id", "5", "-o", out)
        self.assertEqual(code, 0, stdout)
        db = self.read_json(out)
        self.assertEqual(db["title"], "Row B")
        self.assertEqual([p["id"] for p in db["panels"]], [101, 102, 103])
        self.assertEqual(db["panels"][0]["type"], "row")
        self.assertFalse(db["panels"][0]["collapsed"])
        self.assertEqual([p["title"] for p in db["panels"][1:]], ["B1", "B2"])
        self.assertIsNone(db["id"])
        self.assertEqual(db["version"], 1)
        self.assertEqual(len(db["uid"]), 9)

    def test_riga_collassata_mantiene_i_figli_annidati(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("extract", "row", src, "--match-title", "Row A", "-o", out)
        db = self.read_json(out)
        self.assertEqual(len(db["panels"]), 1)
        self.assertTrue(db["panels"][0]["collapsed"])
        self.assertEqual([p["id"] for p in db["panels"][0]["panels"]], [102, 103])

    def test_pannello(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("extract", "panel", src, "--id", "2", "-o", out)
        self.assertEqual(code, 0, stdout)
        db = self.read_json(out)
        self.assertEqual(db["title"], "A1")
        self.assertEqual(len(db["panels"]), 1)
        self.assertEqual(db["panels"][0]["id"], 101)
        self.assertEqual(db["panels"][0]["title"], "A1")
        self.assertEqual(db["panels"][0]["gridPos"]["y"], 0)
        self.assertEqual(db["panels"][0]["gridPos"]["w"], 12)
        self.assertIsNone(db["id"])
        self.assertEqual(len(db["uid"]), 9)

    def test_titolo_and_base_id(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("extract", "panel", src, "--id", "2", "--title", "Estratto",
                     "--base-id", "900", "-o", out)
        estratto = self.read_json(out)
        self.assertEqual(estratto["title"], "Estratto")
        self.assertEqual(all_ids(estratto), [900])

    def test_un_solo_oggetto_alla_volta(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("extract", "panel", src, "--match-type", "timeseries",
                                    "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("un solo oggetto", err)

    def test_uid_in_conflitto(self):
        src = self.write_json("in.json", sample_dashboard())
        inv = self.write_json("inv.json", [{"uid": "abc123XYZ", "title": "Altra"}])
        code, _, err = self.run_cli("extract", "row", src, "--id", "5",
                                    "--existing-dashboards", inv,
                                    "--uid", "abc123XYZ", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("già usato", err)

    def test_titolo_disambiguato_con_l_inventario(self):
        src = self.write_json("in.json", sample_dashboard())
        inv = self.write_json("inv.json", {"dashboards": [{"uid": "u1", "title": "Row B"}]})
        out = self.tmp / "out.json"
        self.run_cli("extract", "row", src, "--id", "5",
                     "--existing-dashboards", inv, "-o", out)
        self.assertEqual(self.read_json(out)["title"], "Row B (2)")

    def test_output_predefinito(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, _ = self.run_cli("extract", "panel", src, "--id", "2")
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "in_out.json").exists())

    def test_dry_run(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("extract", "panel", src, "--id", "2",
                                  "-o", out, "--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(out.exists())


class SymmetryTest(CLITestCase):
    """Gli stessi verbi e gli stessi nomi di opzione valgono per entrambi i tipi."""

    def test_update_accetta_le_stesse_impostazioni(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        for kind, obj_id in (("row", "1"), ("panel", "2")):
            code, stdout, err = self.run_cli(
                "update", kind, src, "--id", obj_id, "--title", f"T-{kind}",
                "--replace", "up=down", "-o", out,
            )
            self.assertEqual(code, 0, err)
            self.assertIn(f"titolo 'T-{kind}'", stdout)

    def test_delete_accetta_gli_stessi_selettori(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        for kind, obj_id in (("row", "9"), ("panel", "100")):
            code, _, err = self.run_cli("delete", kind, src, "--id", obj_id, "-o", out)
            self.assertEqual(code, 0, err)

    def test_list_accetta_gli_stessi_selettori(self):
        src = self.write_json("in.json", sample_dashboard())
        for kind in ("row", "panel"):
            code, out, err = self.run_cli("list", kind, src, "--format", "json",
                                          "--match-title", ".")
            self.assertEqual(code, 0, err)
            self.assertIsInstance(json.loads(out), list)

    def test_estrazione_valida_per_entrambi_i_tipi(self):
        src = self.write_json("in.json", sample_dashboard())
        for kind, obj_id in (("row", "5"), ("panel", "2")):
            out = self.tmp / f"{kind}.json"
            code, stdout, err = self.run_cli("extract", kind, src,
                                             "--id", obj_id, "-o", out)
            self.assertEqual(code, 0, err)
            code_validate, report, _ = self.run_cli("validate", str(out))
            self.assertEqual(code_validate, 0, report)


if __name__ == "__main__":
    unittest.main()
