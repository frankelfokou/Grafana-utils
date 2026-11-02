"""Test dei comandi di scrittura, uno per comando, con casi felici ed errori."""
from __future__ import annotations

import json
import unittest

from grafana_tool.model import find_row, row_children
from tests.support import CLITestCase, all_ids, panel, row, sample_dashboard


class DuplicateRowTest(CLITestCase):
    def test_duplica_riga_collassata(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("duplicate-row", src, "--source", "1", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn('creata dopo la riga 1, con 2 pannelli', stdout)
        db = self.read_json(out)
        titles = [p.get("title") for p in db["panels"]]
        self.assertIn("Row A_COPY", titles)
        self.assertEqual(titles.index("Row A_COPY"), titles.index("Row A") + 1)
        copia = find_row(db, 101)
        self.assertTrue(copia["collapsed"])
        self.assertEqual(len(copia["panels"]), 2)

    def test_duplica_riga_espansa_includendo_i_fratelli(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("duplicate-row", src, "--source", "5", "-o", out)
        self.assertEqual(code, 0)
        db = self.read_json(out)
        titles = [p.get("title") for p in db["panels"]]
        # la nuova riga va dopo i fratelli B1 e B2, non subito dopo Row B
        self.assertEqual(titles[3:6], ["B1", "B2", "Row B_COPY"])
        copia = find_row(db, 101)
        self.assertEqual(len(copia["panels"]), 2)
        self.assertEqual(len(set(all_ids(db))), len(all_ids(db)))

    def test_titolo_e_sostituzioni(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli(
            "duplicate-row", src, "--source", "5", "--new-title", "Copia",
            "--replace", "up=down", "-o", out,
        )
        self.assertEqual(code, 0)
        db = self.read_json(out)
        copia = find_row(db, 101)
        self.assertEqual(copia["title"], "Copia")
        self.assertEqual(copia["panels"][0]["targets"][0]["expr"], 'down{panel="6"}')

    def test_titoli_dei_cloni_invariati_per_default(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("duplicate-row", src, "--source", "1", "-o", out)
        copia = find_row(self.read_json(out), 101)
        self.assertEqual([p["title"] for p in copia["panels"]], ["A1", "A2"])

    def test_dedupe_titles_opzionale(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("duplicate-row", src, "--source", "1",
                     "--dedupe-titles", "-o", out)
        copia = find_row(self.read_json(out), 101)
        self.assertEqual([p["title"] for p in copia["panels"]],
                         ["A1 (2)", "A2 (2)"])

    def test_titolo_della_copia_reso_unico_con_dedupe(self):
        db = sample_dashboard()
        db["panels"].append(row(50, "Row A_COPY"))
        src = self.write_json("in.json", db)
        out = self.tmp / "out.json"
        self.run_cli("duplicate-row", src, "--source", "1",
                     "--dedupe-titles", "-o", out)
        copia = find_row(self.read_json(out), 101)
        self.assertEqual(copia["title"], "Row A_COPY (2)")

    def test_riga_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("duplicate-row", src, "--source", "999", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("non trovata", err)

    def test_output_predefinito(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, _ = self.run_cli("duplicate-row", src, "--source", "1")
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "in_out.json").exists())


class CopyPanelTest(CLITestCase):
    def test_copia_nella_stessa_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("copy-panel", src, "--panel-id", "2", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("Pannello 2 copiato come id 101", stdout)
        db = self.read_json(out)
        self.assertEqual([p["id"] for p in find_row(db, 1)["panels"]], [2, 101, 3])

    def test_copia_in_riga_espansa_va_dopo_i_fratelli(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("copy-panel", src, "--panel-id", "2",
                                  "--target-row", "5", "-o", out)
        self.assertEqual(code, 0)
        db = self.read_json(out)
        ids = [p["id"] for p in db["panels"]]
        self.assertEqual(ids[-2:], [101, 9])
        self.assertEqual(len(row_children(db, find_row(db, 5))), 3)

    def test_titolo_e_query_nuovi(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("copy-panel", src, "--panel-id", "2", "--new-title", "N",
                     "--replace", "up=down", "-o", out)
        db = self.read_json(out)
        clone = find_row(db, 1)["panels"][1]
        self.assertEqual(clone["title"], "N")
        self.assertEqual(clone["targets"][0]["expr"], 'down{panel="2"}')

    def test_dedupe_titles_opzionale(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("copy-panel", src, "--panel-id", "2",
                     "--dedupe-titles", "-o", out)
        db = self.read_json(out)
        clone = find_row(db, 1)["panels"][1]
        self.assertEqual(clone["title"], "A1 (2)")

    def test_non_copia_righe(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("copy-panel", src, "--panel-id", "5", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("non copia righe", err)

    def test_pannello_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, _ = self.run_cli("copy-panel", src, "--panel-id", "999", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)

    def test_riga_destinazione_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, _ = self.run_cli("copy-panel", src, "--panel-id", "2",
                                  "--target-row", "999", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)


class MovePanelTest(CLITestCase):
    def test_sposta_in_riga_collassata(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("move-panel", src, "--panel-id", "6",
                                       "--target-row", "1", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("Pannello 6 spostato nella riga 1", stdout)
        db = self.read_json(out)
        self.assertEqual([p["id"] for p in find_row(db, 1)["panels"]], [2, 3, 6])

    def test_sposta_in_riga_espansa(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("move-panel", src, "--panel-id", "2",
                                  "--target-row", "5", "-o", out)
        self.assertEqual(code, 0)
        db = self.read_json(out)
        self.assertEqual([p["id"] for p in row_children(db, find_row(db, 5))], [6, 7, 2])

    def test_pannello_gia_nella_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("move-panel", src, "--panel-id", "6",
                                    "--target-row", "5", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("già nella riga", err)

    def test_pannello_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        self.assertEqual(self.run_cli("move-panel", src, "--panel-id", "999",
                                      "--target-row", "1", "-o", self.tmp / "o.json")[0], 1)

    def test_riga_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        self.assertEqual(self.run_cli("move-panel", src, "--panel-id", "2",
                                      "--target-row", "999", "-o", self.tmp / "o.json")[0], 1)

    def test_riga_non_spostabile(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("move-panel", src, "--panel-id", "1",
                                    "--target-row", "5", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("non sposta righe", err)


class ReplaceTest(CLITestCase):
    def test_globale(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("replace", src, "--replace", "up=down", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("Sostituzioni applicate a 5 target.", stdout)
        db = self.read_json(out)
        self.assertTrue(all("down{" in p["targets"][0]["expr"] for p in row_children(db, find_row(db, 1))))

    def test_limitata_a_una_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("replace", src, "--replace", "up=down",
                                       "--row", "5", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Sostituzioni applicate a 2 target.", stdout)

    def test_riga_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, _ = self.run_cli("replace", src, "--replace", "a=b", "--row", "999",
                                  "--dry-run")
        self.assertEqual(code, 1)

    def test_replace_malformato(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("replace", src, "--replace", "senza-uguale")
        self.assertEqual(code, 1)
        self.assertIn("OLD=NEW", err)


class TransformTest(CLITestCase):
    def test_per_tipo(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("transform", src, "--match-type", "timeseries", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("Pannelli corrispondenti: 4.", stdout)

    def test_per_titolo(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("transform", src, "--match-title", "^B", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Pannelli corrispondenti: 2.", stdout)

    def test_titolo_case_insensitive(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("transform", src, "--match-title", "^b1$", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Pannelli corrispondenti: 1.", stdout)

    def test_tipo_case_insensitive(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("transform", src, "--match-type", "TIMESERIES", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Pannelli corrispondenti: 4.", stdout)

    def test_datasource_e_titolo(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("transform", src, "--match-type", "timeseries",
                                  "--ds-uid", "nuovo", "--new-title", "T", "-o", out)
        self.assertEqual(code, 0)
        db = self.read_json(out)
        for p in db["panels"][1]["panels"]:
            self.assertEqual(p["title"], "T")
            self.assertEqual(p["datasource"]["uid"], "nuovo")
            self.assertEqual(p["targets"][0]["datasource"]["uid"], "nuovo")

    def test_richiede_un_criterio(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("transform", src, "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("almeno --match-type o --match-title", err)

    def test_non_modifica_le_righe(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("transform", src, "--match-type", "timeseries", "--new-title", "T", "-o", out)
        db = self.read_json(out)
        self.assertEqual(find_row(db, 5)["title"], "Row B")


class PruneTest(CLITestCase):
    def test_per_id(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("prune", src, "--panel-id", "2", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("Pannelli rimossi: 1.", stdout)
        self.assertEqual([p["id"] for p in find_row(self.read_json(out), 1)["panels"]], [3])

    def test_per_tipo(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("prune", src, "--match-type", "text", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Pannelli rimossi: 1.", stdout)

    def test_per_titolo(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("prune", src, "--match-title", "^B", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("Pannelli rimossi: 2.", stdout)
        self.assertEqual(len(row_children(self.read_json(out), find_row(self.read_json(out), 5))), 0)

    def test_titolo_case_insensitive(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("prune", src, "--match-title", "^b1$", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Pannelli rimossi: 1.", stdout)

    def test_tipo_case_insensitive(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("prune", src, "--match-type", "TEXT", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Pannelli rimossi: 1.", stdout)

    def test_non_rimuove_le_righe(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("prune", src, "--panel-id", "5", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Pannelli rimossi: 0.", stdout)

    def test_richiede_un_criterio(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, _ = self.run_cli("prune", src, "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertEqual(len(self.logs("command")), 1)


class SetDatasourceTest(CLITestCase):
    def test_globale(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("set-datasource", src, "--uid", "nuovo",
                                       "--type", "prometheus", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("Datasource aggiornato in 10 punti.", stdout)
        db = self.read_json(out)
        self.assertEqual(db["panels"][0]["datasource"]["uid"], "nuovo")

    def test_limitata_a_una_riga(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("set-datasource", src, "--uid", "nuovo",
                                       "--row", "5", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Datasource aggiornato in 4 punti.", stdout)

    def test_force_crea_il_blocco(self):
        p = {"id": 1, "type": "text", "title": "x"}
        src = self.write_json("in.json", {"panels": [p]})
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("set-datasource", src, "--uid", "u", "--force", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("1 punti", stdout)
        self.assertEqual(self.read_json(out)["panels"][0]["datasource"], {"type": "prometheus", "uid": "u"})

    def test_senza_force_salta_i_blocchi_assenti(self):
        src = self.write_json("in.json", {"panels": [{"id": 1, "type": "text", "title": "x"}]})
        code, stdout, _ = self.run_cli("set-datasource", src, "--uid", "u", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("0 punti", stdout)


class ReflowTest(CLITestCase):
    def test_tutte_le_righe(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("reflow", src, "-o", out)
        self.assertEqual(code, 0)
        # i pannelli top-level fuori riga (100) non vengono toccati
        self.assertIn("Reflow applicato a 4 pannelli.", stdout)
        db = self.read_json(out)
        # riga espansa: i figli partono sotto l'intestazione, la riga resta espansa
        self.assertFalse(find_row(db, 5)["collapsed"])
        self.assertEqual(row_children(db, find_row(db, 5))[0]["gridPos"]["y"], 1)
        # riga collassata: i figli partono da 0 e la riga resta collassata
        self.assertTrue(find_row(db, 1)["collapsed"])
        self.assertEqual(find_row(db, 1)["panels"][0]["gridPos"]["y"], 0)

    def test_su_riga_espansa(self):
        src = self.write_json("in.json", sample_dashboard())
        code, stdout, _ = self.run_cli("reflow", src, "--row", "5", "--dry-run")
        self.assertEqual(code, 0)
        self.assertIn("Reflow applicato a 2 pannelli.", stdout)

    def test_a_capo_oltre_le_colonne(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("reflow", src, "--row", "1", "--columns", "12", "-o", out)
        db = self.read_json(out)
        pan = find_row(db, 1)["panels"]
        self.assertEqual((pan[0]["gridPos"]["x"], pan[0]["gridPos"]["y"]), (0, 0))
        self.assertEqual((pan[1]["gridPos"]["x"], pan[1]["gridPos"]["y"]), (0, 8))

    def test_riga_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        self.assertEqual(self.run_cli("reflow", src, "--row", "999", "--dry-run")[0], 1)

    def test_colonne_non_valide(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("reflow", src, "--columns", "0", "--dry-run")
        self.assertEqual(code, 1)
        self.assertIn("> 0", err)


class AppendRowTest(CLITestCase):
    def test_da_dashboard_espansa(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("append-row", src, "--from-dashboard", src,
                                       "--row-match", "Row B", "--on-existing", "append", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("2 pannelli", stdout)
        db = self.read_json(out)
        nuova = db["panels"][-1]
        self.assertEqual(nuova["title"], "VISTA SISTEMISTICA - universo-on-line-feu-up")
        self.assertTrue(nuova["collapsed"])
        self.assertEqual(len(nuova["panels"]), 2)

    def test_template_predefinito(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("append-row", src, "-o", out)
        self.assertEqual(code, 0)
        db = self.read_json(out)
        nuova = db["panels"][-1]
        self.assertEqual(len(nuova["panels"]), 16)
        self.assertNotIn("${", json.dumps(nuova))
        exprs = [t.get("expr", "") for p in nuova["panels"] for t in p.get("targets") or []]
        self.assertTrue(any('namespace=~"universo-on-line-feu-up"' in e for e in exprs))

    def test_template_con_parametri(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("append-row", src, "--namespace", "pa-digital", "--cluster-gen", "3",
                     "--row-title", "TEST", "--no-normalize", "--base-id", "500", "-o", out)
        db = self.read_json(out)
        nuova = db["panels"][-1]
        self.assertEqual(nuova["id"], 500)
        self.assertEqual(nuova["panels"][0]["id"], 501)
        self.assertEqual(nuova["title"], "TEST")
        exprs = [t.get("expr", "") for p in nuova["panels"] for t in p.get("targets") or []]
        self.assertTrue(any('namespace="pa-digital"' in e for e in exprs))
        self.assertTrue(any('cluster_gen="3"' in e for e in exprs))

    def test_parametri_da_file(self):
        src = self.write_json("in.json", sample_dashboard())
        params = self.write_json("p.json", {"NAMESPACE": "da-file", "ROW_TITLE": "T-file"})
        out = self.tmp / "out.json"
        self.run_cli("append-row", src, "--params", params, "-o", out)
        nuova = self.read_json(out)["panels"][-1]
        self.assertEqual(nuova["title"], "T-file")
        self.assertIn("da-file", json.dumps(nuova))

    def test_on_existing_skip(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("append-row", src, "--from-dashboard", src,
                                       "--row-match", "Row B", "--on-existing", "skip", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("skip", stdout)
        self.assertEqual(len(self.read_json(out)["panels"]), 6)

    def test_on_existing_error(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("append-row", src, "--from-dashboard", src,
                                    "--row-match", "Row B", "--on-existing", "error",
                                    "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("Row esistente", err)

    def test_on_existing_replace_rimuove_anche_i_fratelli(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("append-row", src, "--from-dashboard", src,
                                  "--row-match", "Row B", "--on-existing", "replace", "-o", out)
        self.assertEqual(code, 0)
        db = self.read_json(out)
        self.assertIsNone(find_row(db, 5))
        self.assertEqual([p["id"] for p in db["panels"] if p["type"] != "row"], [100])

    def test_posizione_in_cima(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("append-row", src, "--from-dashboard", src, "--row-match", "Row B",
                     "--position", "top", "-o", out)
        db = self.read_json(out)
        self.assertEqual(db["panels"][0]["title"], "VISTA SISTEMISTICA - universo-on-line-feu-up")

    def test_riga_espansa(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("append-row", src, "--from-dashboard", src, "--row-match", "Row B",
                     "--expanded", "-o", out)
        db = self.read_json(out)
        nuova = db["panels"][-3]
        self.assertFalse(nuova["collapsed"])
        self.assertEqual(nuova["panels"], [])
        self.assertEqual(len(row_children(db, nuova)), 2)

    def test_base_id_in_conflitto(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("append-row", src, "--base-id", "100",
                                    "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("collide", err)

    def test_dedupe_titles_opzionale(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("append-row", src, "--from-dashboard", src, "--row-match", "Row B",
                     "--on-existing", "append", "--dedupe-titles", "-o", out)
        nuova = self.read_json(out)["panels"][-1]
        self.assertEqual([p["title"] for p in nuova["panels"]],
                         ["B1 (2)", "B2 (2)"])

    def test_row_match_senza_risultati(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("append-row", src, "--from-dashboard", src,
                                    "--row-match", "nope", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("Nessuna row", err)

    def test_row_match_case_insensitive(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("append-row", src, "--from-dashboard", src,
                                  "--row-match", "row b", "--on-existing", "append", "-o", out)
        self.assertEqual(code, 0)
        self.assertEqual(len(self.read_json(out)["panels"][-1]["panels"]), 2)

    def test_template_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, _ = self.run_cli("append-row", src, "--template", str(self.tmp / "nope.json"),
                                  "-o", self.tmp / "o.json")
        self.assertEqual(code, 2)


class ExtractRowTest(CLITestCase):
    def test_riga_espansa_include_i_fratelli(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("extract-row", "--from-dashboard", src,
                                       "--row-id", "5", "-o", out)
        self.assertEqual(code, 0)
        self.assertIn("2 pannelli", stdout)
        db = self.read_json(out)
        self.assertEqual(db["title"], "Row B")
        # base = max id della sorgente (100) + 1: gli id dell'output non
        # riusano quelli già presenti nella dashboard di partenza
        self.assertEqual([p["id"] for p in db["panels"]], [101, 102, 103])
        self.assertEqual(db["panels"][0]["type"], "row")
        self.assertFalse(db["panels"][0]["collapsed"])
        self.assertEqual([p["title"] for p in db["panels"][1:]], ["B1", "B2"])
        self.assertIsNone(db["id"])
        self.assertEqual(db["version"], 1)
        self.assertIsInstance(db["uid"], str)
        self.assertEqual(len(db["uid"]), 9)

    def test_riga_collassata_mantiene_i_figli_annidati(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("extract-row", "--from-dashboard", src,
                                  "--row-match", "Row A", "-o", out)
        self.assertEqual(code, 0)
        db = self.read_json(out)
        self.assertEqual(len(db["panels"]), 1)
        riga = db["panels"][0]
        self.assertTrue(riga["collapsed"])
        self.assertEqual([p["id"] for p in riga["panels"]], [102, 103])

    def test_id_rinumerati_e_unici(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("extract-row", "--from-dashboard", src, "--row-id", "5", "-o", out)
        ids = all_ids(self.read_json(out))
        self.assertEqual(ids, [101, 102, 103])

    def test_uid_nuovo_e_diverso_dalla_sorgente(self):
        db = sample_dashboard()
        db["uid"] = "syS96Y-Iz"
        src = self.write_json("in.json", db)
        out = self.tmp / "out.json"
        self.run_cli("extract-row", "--from-dashboard", src, "--row-id", "5", "-o", out)
        estratto = self.read_json(out)
        self.assertNotEqual(estratto["uid"], "syS96Y-Iz")
        self.assertEqual(len(estratto["uid"]), 9)

    def test_uid_esplicito_in_conflitto_e_un_errore(self):
        src = self.write_json("in.json", sample_dashboard())
        inv = self.write_json("inv.json", [{"uid": "abc123XYZ", "title": "Altra"}])
        code, _, err = self.run_cli("extract-row", "--from-dashboard", src, "--row-id", "5",
                                    "--existing-dashboards", inv, "--uid", "abc123XYZ",
                                    "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("già usato", err)

    def test_titolo_disambiguato_rispetto_all_inventario(self):
        src = self.write_json("in.json", sample_dashboard())
        inv = self.write_json("inv.json", {"dashboards": [{"uid": "u1", "title": "Row B"}]})
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("extract-row", "--from-dashboard", src, "--row-id", "5",
                                  "--existing-dashboards", inv, "-o", out)
        self.assertEqual(code, 0)
        self.assertEqual(self.read_json(out)["title"], "Row B (2)")

    def test_titolo_e_base_id_espliciti(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        self.run_cli("extract-row", "--from-dashboard", src, "--row-id", "5",
                     "--title", "Estratta", "--panel-id-base", "900", "-o", out)
        estratto = self.read_json(out)
        self.assertEqual(estratto["title"], "Estratta")
        self.assertEqual(all_ids(estratto), [900, 901, 902])

    def test_grid_pos_normalizzata(self):
        db = sample_dashboard()
        db["panels"][2]["gridPos"] = {"h": 1, "w": 24, "x": 0, "y": 10}
        db["panels"][3]["gridPos"] = {"h": 8, "w": 12, "x": 0, "y": 11}
        db["panels"][4]["gridPos"] = {"h": 8, "w": 12, "x": 12, "y": 19}
        src = self.write_json("in.json", db)
        out = self.tmp / "out.json"
        self.run_cli("extract-row", "--from-dashboard", src, "--row-id", "5", "-o", out)
        est = self.read_json(out)
        self.assertEqual(est["panels"][0]["gridPos"]["y"], 0)
        self.assertEqual(est["panels"][1]["gridPos"]["y"], 1)
        self.assertEqual(est["panels"][2]["gridPos"]["y"], 9)

    def test_nessun_match(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("extract-row", "--from-dashboard", src,
                                    "--row-match", "nope", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)
        self.assertIn("Nessuna row", err)

    def test_row_id_inesistente(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, _ = self.run_cli("extract-row", "--from-dashboard", src,
                                  "--row-id", "999", "-o", self.tmp / "o.json")
        self.assertEqual(code, 1)

    def test_output_predefinito(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, _ = self.run_cli("extract-row", "--from-dashboard", src, "--row-id", "5")
        self.assertEqual(code, 0)
        self.assertTrue((self.tmp / "in_out.json").exists())

    def test_dry_run(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, _ = self.run_cli("extract-row", "--from-dashboard", src,
                                  "--row-id", "5", "-o", out, "--dry-run")
        self.assertEqual(code, 0)
        self.assertFalse(out.exists())

    def test_row_match_case_insensitive(self):
        src = self.write_json("in.json", sample_dashboard())
        out = self.tmp / "out.json"
        code, _, err = self.run_cli("extract-row", "--from-dashboard", src,
                                    "--row-match", "row b", "-o", out)
        self.assertEqual(code, 0, err)
        self.assertEqual(self.read_json(out)["title"], "Row B")


if __name__ == "__main__":
    unittest.main()
