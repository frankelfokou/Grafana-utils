"""Test che le variabili della dashboard non vengano mai alterate.

Le variabili sono contesto di esecuzione condiviso: cambiarle significa
cambiare il significato di tutte le query. I comandi non devono toccarle, e
una conversione tra formati deve solo ri-esprimerle, mai riscriverle.

Questi test sono la garanzia: se qualcuno tocca `templating` o `variables`
per errore, falliscono.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from grafana_tool import formats, schema

from support import CLITestCase, panel, sample_dashboard

FIXTURES = Path(__file__).resolve().parent / "fixtures"
V2_FIXTURE = FIXTURES / "dashboard-v2.json"


def v2_doc() -> dict:
    return json.loads(V2_FIXTURE.read_text(encoding="utf-8"))


def classic_list(doc: dict) -> list:
    """`templating.list` di un documento classico."""
    templating = doc.get("templating")
    if isinstance(templating, dict):
        return templating.get("list") or []
    if isinstance(templating, list):
        return templating
    return []


def v2_list(doc: dict) -> list:
    return doc.get("variables") or []


def classic_with_variables() -> dict:
    """Dashboard classica con i tipi di variabile più comuni."""
    db = sample_dashboard()
    db["uid"] = "orig00001"
    db["title"] = "Con variabili"
    db["templating"] = {
        "list": [
            {
                "name": "env",
                "type": "datasource",
                "query": "prometheus",
                "current": {"text": "Prom", "value": "prom-uid"},
                # Gli enum del classico sono numeri: 2 = hideVariable.
                "hide": 2,
                "includeAll": False,
                "multi": False,
                "options": [],
                "refresh": 1,
                "regex": "",
                "skipUrlSync": False,
            },
            {
                "name": "cluster_gen",
                "type": "query",
                "query": "label_values(cluster_gen)",
                "definition": "label_values(cluster_gen)",
                "current": {"text": "3", "value": "3"},
                "hide": 0,
                "includeAll": False,
                "multi": False,
                "options": [],
                "refresh": 1,
                "regex": "/^(2|3)$/",
                "skipUrlSync": False,
                "sort": 0,
                "datasource": {"type": "prometheus", "uid": "prom-uid"},
            },
        ]
    }
    return db


class ClassicCommandsTest(CLITestCase):
    """I comandi su una dashboard classica lasciano `templating` intatto."""

    def _vars(self, path: str) -> list:
        return classic_list(self.read_json(path))

    def test_update_row(self) -> None:
        src = self.write_json("in.json", classic_with_variables())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "update", "row", "--id", "5", "--title", "Rinominata", src, "-o", out
        )
        self.assertEqual(code, 0, stdout)
        self.assertEqual(self._vars(str(out)), classic_list(classic_with_variables()))

    def test_update_panel_con_replace(self) -> None:
        src = self.write_json("in.json", classic_with_variables())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "update", "panel", "--id", "2", "--replace", "up=down", src, "-o", out
        )
        self.assertEqual(code, 0, stdout)
        self.assertEqual(self._vars(str(out)), classic_list(classic_with_variables()))

    def test_delete_panel(self) -> None:
        src = self.write_json("in.json", classic_with_variables())
        out = self.tmp / "out.json"
        self.run_cli("delete", "panel", "--id", "3", src, "-o", out)
        self.assertEqual(self._vars(str(out)), classic_list(classic_with_variables()))

    def test_move_panel(self) -> None:
        src = self.write_json("in.json", classic_with_variables())
        out = self.tmp / "out.json"
        self.run_cli("move", "panel", "--id", "2", "--to-row", "5", src, "-o", out)
        self.assertEqual(self._vars(str(out)), classic_list(classic_with_variables()))

    def test_layout(self) -> None:
        src = self.write_json("in.json", classic_with_variables())
        out = self.tmp / "out.json"
        self.run_cli("layout", src, "-o", out)
        self.assertEqual(self._vars(str(out)), classic_list(classic_with_variables()))

    def test_fork(self) -> None:
        src = self.write_json("in.json", classic_with_variables())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("fork", src, "-o", out)
        self.assertEqual(code, 0, stdout)
        self.assertEqual(self._vars(str(out)), classic_list(classic_with_variables()))


class V2CommandsTest(CLITestCase):
    """I comandi su una dashboard v2 lasciano `variables` intatto."""

    def test_update_tab(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "update", "tab", "--id", "2", "--title", "Sistemistica",
            str(V2_FIXTURE), "-o", out,
        )
        self.assertEqual(code, 0, stdout)
        self.assertEqual(v2_list(self.read_json(out)), v2_list(v2_doc()))

    def test_fork(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("fork", str(V2_FIXTURE), "-o", out)
        self.assertEqual(code, 0, stdout)
        self.assertEqual(v2_list(self.read_json(out)), v2_list(v2_doc()))

    def test_delete_tab(self) -> None:
        out = self.tmp / "out.json"
        self.run_cli("delete", "tab", "--id", "1", "--keep-children",
                     str(V2_FIXTURE), "-o", out)
        self.assertEqual(v2_list(self.read_json(out)), v2_list(v2_doc()))

    def test_uscita_classica(self) -> None:
        """La conversione ri-esprime le variabili, non le riscrive."""
        db = formats.load(v2_doc()).db
        out, _ = formats.render(db, schema.CLASSIC)
        variabili = classic_list(out)
        self.assertEqual([v["name"] for v in variabili], ["env", "cluster_gen"])
        self.assertEqual(variabili[0]["type"], "datasource")
        self.assertEqual(variabili[0]["query"], "prometheus")
        self.assertEqual(variabili[1]["type"], "query")
        self.assertEqual(variabili[1]["query"]["query"], "label_values(cluster_gen)")
        self.assertEqual(variabili[1]["datasource"],
                         {"type": "prometheus", "uid": "prom-main"})

    def test_enum_numerici_nel_classico(self) -> None:
        """`hide`, `refresh` e `sort` sono numeri: Grafana li legge così.

        Con `hide` come stringa l'etichetta del selettore sparisce, perché
        `"dontHide"` non è uguale a 0.
        """
        db = formats.load(v2_doc()).db
        out, _ = formats.render(db, schema.CLASSIC)
        env, cluster = classic_list(out)
        self.assertEqual(env["hide"], 2)
        self.assertEqual(env["refresh"], 1)
        self.assertEqual(cluster["hide"], 0)
        self.assertEqual(cluster["refresh"], 1)
        self.assertEqual(cluster["sort"], 0)

    def test_enum_testuali_in_v2(self) -> None:
        db = formats.load(v2_doc()).db
        out, _ = formats.render(db, schema.V2)
        env, cluster = v2_list(out)
        self.assertEqual(env["spec"]["hide"], "hideVariable")
        self.assertEqual(cluster["spec"]["hide"], "dontHide")
        self.assertEqual(cluster["spec"]["sort"], "disabled")


class RoundTripTest(unittest.TestCase):
    """Giro completo tra formati: le variabili tornano identiche."""

    def test_v2_classico_v2(self) -> None:
        db = formats.load(copy.deepcopy(v2_doc())).db
        out, _ = formats.render(copy.deepcopy(db), schema.CLASSIC)
        back, _ = formats.render(formats.load(out).db, schema.V2)
        self.assertEqual(v2_list(back), v2_list(v2_doc()))

    def test_classico_v2_classico(self) -> None:
        originale = classic_with_variables()
        db = formats.load(copy.deepcopy(originale)).db
        out, _ = formats.render(db, schema.V2)
        back, _ = formats.render(formats.load(out).db, schema.CLASSIC)
        self.assertEqual(classic_list(back), classic_list(originale))

    def test_query_in_forma_di_stringa(self) -> None:
        """La forma classica della query non cambia con il giro."""
        originale = {
            "name": "x", "type": "query", "query": "label_values(up)",
            "datasource": {"type": "prometheus", "uid": "p1"},
        }
        doc = {"title": "T", "panels": [], "templating": {"list": [originale]}}
        v2, _ = formats.render(formats.load(copy.deepcopy(doc)).db, schema.V2)
        back, _ = formats.render(formats.load(v2).db, schema.CLASSIC)
        self.assertEqual(classic_list(back), [originale])

    def test_query_in_forma_di_oggetto(self) -> None:
        originale = {
            "name": "x", "type": "query",
            "query": {"query": "label_values(up)", "refId": "A"},
            "datasource": {"type": "prometheus", "uid": "p1"},
        }
        doc = {"title": "T", "panels": [], "templating": {"list": [originale]}}
        v2, _ = formats.render(formats.load(copy.deepcopy(doc)).db, schema.V2)
        back, _ = formats.render(formats.load(v2).db, schema.CLASSIC)
        self.assertEqual(classic_list(back), [originale])

    def test_appiattimento_non_tocca_le_variabili(self) -> None:
        db = formats.load(copy.deepcopy(v2_doc())).db
        prima = copy.deepcopy(v2_list(formats.render(copy.deepcopy(db), schema.V2)[0]))
        out, _ = formats.render(copy.deepcopy(db), schema.CLASSIC)
        self.assertEqual([v["name"] for v in classic_list(out)], ["env", "cluster_gen"])
        dopo = v2_list(formats.render(formats.load(out).db, schema.V2)[0])
        self.assertEqual(dopo, prima)


class ExtractTest(CLITestCase):
    """`extract` eredita le variabili: è una scelta, non una svista."""

    def test_estrazione_conserva_le_variabili(self) -> None:
        src = self.write_json("in.json", classic_with_variables())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "extract", "panel", "--id", "2", src, "-o", out
        )
        self.assertEqual(code, 0, stdout)
        self.assertEqual(classic_list(self.read_json(out)),
                         classic_list(classic_with_variables()))

    def test_pannello_struttura_di_controllo(self) -> None:
        """Il pannello usato dai test esiste e ha una query."""
        db = sample_dashboard()
        self.assertIn("targets", panel(2, "A1"))


if __name__ == "__main__":
    unittest.main()
