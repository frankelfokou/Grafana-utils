"""Test delle regole sulle variabili.

Tre contratti, in ordine di forza:

  1. i comandi non cambiano valori, definizioni e tipi delle variabili;
  2. in uscita le variabili sono **visibili in alto** (`hide` azzerato), anche
     se nella dashboard di origine erano nascoste — `--keep-variable-visibility`
     conserva la scelta originale;
  3. nei pannelli un valore fisso che ha il nome di una variabile viene
     sostituito dal riferimento (`cluster_gen="3"` → `cluster_gen="$cluster_gen"`)
     — `--keep-literal-values` lo lascia com'è.
"""
from __future__ import annotations

import copy
import json
import re
import unittest
from pathlib import Path

from grafana_tool import formats, model, schema
from grafana_tool.formats import variables as variables_module

from tests.support import CLITestCase, sample_dashboard

FIXTURES = Path(__file__).resolve().parent / "fixtures"
V2_FIXTURE = FIXTURES / "dashboard-v2.json"

LITERALE = re.compile(r'cluster_gen\s*(=~|!~|=|!=)\s*"(?!\$)[^"]*"')


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


def without_hide(variables: list) -> list:
    """Le variabili classiche senza `hide`: il resto non deve mai cambiare."""
    return [{k: v for k, v in variable.items() if k != "hide"} for variable in variables]


def without_hide_v2(variables: list) -> list:
    """Le variabili v2 senza `spec.hide`."""
    fuori = []
    for variable in variables:
        copia = copy.deepcopy(variable)
        spec = copia.get("spec")
        if isinstance(spec, dict):
            spec.pop("hide", None)
        fuori.append(copia)
    return fuori


def is_visible(value) -> bool:
    return value in (0, "dontHide")


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
    """I comandi su una dashboard classica non toccano le variabili."""

    def _check(self, *argv: str) -> dict:
        src = self.write_json("in.json", classic_with_variables())
        out = self.tmp / "out.json"
        code, stdout, err = self.run_cli(*argv, src, "-o", out)
        self.assertEqual(code, 0, stdout + err)
        scritto = self.read_json(out)
        originale = classic_list(classic_with_variables())
        self.assertEqual(without_hide(classic_list(scritto)), without_hide(originale))
        return scritto

    def test_update_row(self) -> None:
        self._check("update", "row", "--id", "5", "--title", "Rinominata")

    def test_update_panel_con_replace(self) -> None:
        self._check("update", "panel", "--id", "2", "--replace", "up=down")

    def test_delete_panel(self) -> None:
        self._check("delete", "panel", "--id", "3")

    def test_move_panel(self) -> None:
        self._check("move", "panel", "--id", "2", "--to-row", "5")

    def test_layout(self) -> None:
        self._check("layout")

    def test_fork(self) -> None:
        self._check("fork")

    def test_variabili_visibili_in_alto(self) -> None:
        """Anche `env`, nascosta nell'origine, esce visibile."""
        scritto = self._check("fork")
        for variabile in classic_list(scritto):
            self.assertTrue(is_visible(variabile["hide"]), variabile["name"])

    def test_keep_variable_visibility(self) -> None:
        src = self.write_json("in.json", classic_with_variables())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "fork", src, "-o", out, "--keep-variable-visibility"
        )
        self.assertEqual(code, 0, stdout)
        self.assertEqual(classic_list(self.read_json(out)),
                         classic_list(classic_with_variables()))


class V2CommandsTest(CLITestCase):
    """I comandi su una dashboard v2 non toccano le variabili."""

    def _check(self, *argv: str) -> dict:
        out = self.tmp / "out.json"
        code, stdout, err = self.run_cli(*argv, str(V2_FIXTURE), "-o", out)
        self.assertEqual(code, 0, stdout + err)
        scritto = self.read_json(out)
        self.assertEqual(without_hide_v2(v2_list(scritto)),
                         without_hide_v2(v2_list(v2_doc())))
        return scritto

    def test_update_tab(self) -> None:
        self._check("update", "tab", "--id", "2", "--title", "Sistemistica")

    def test_fork(self) -> None:
        self._check("fork")

    def test_delete_tab(self) -> None:
        self._check("delete", "tab", "--id", "1", "--keep-children")

    def test_variabili_visibili_in_alto(self) -> None:
        scritto = self._check("fork")
        for variabile in v2_list(scritto):
            self.assertTrue(is_visible(variabile["spec"]["hide"]), variabile["kind"])


class ConversionTest(unittest.TestCase):
    """La conversione ri-esprime le variabili, con gli enum giusti."""

    def test_enum_numerici_nel_classico(self) -> None:
        """`hide`, `refresh` e `sort` sono numeri: Grafana li legge così."""
        db = formats.load(v2_doc()).db
        out, _ = formats.render(db, schema.CLASSIC, keep_variable_visibility=True)
        env, cluster = classic_list(out)
        self.assertEqual(env["hide"], 2)
        self.assertEqual(env["refresh"], 1)
        self.assertEqual(cluster["hide"], 0)
        self.assertEqual(cluster["refresh"], 1)
        self.assertEqual(cluster["sort"], 0)

    def test_enum_testuali_in_v2(self) -> None:
        db = formats.load(v2_doc()).db
        out, _ = formats.render(db, schema.V2, keep_variable_visibility=True)
        env, cluster = v2_list(out)
        self.assertEqual(env["spec"]["hide"], "hideVariable")
        self.assertEqual(cluster["spec"]["hide"], "dontHide")
        self.assertEqual(cluster["spec"]["sort"], "disabled")

    def test_datasource_della_variabile(self) -> None:
        db = formats.load(v2_doc()).db
        out, _ = formats.render(db, schema.CLASSIC, keep_variable_visibility=True)
        env, cluster = classic_list(out)
        self.assertEqual(env["type"], "datasource")
        self.assertEqual(env["query"], "prometheus")
        self.assertEqual(cluster["type"], "query")
        self.assertEqual(cluster["query"]["query"], "label_values(cluster_gen)")
        self.assertEqual(cluster["datasource"],
                         {"type": "prometheus", "uid": "prom-main"})


class RoundTripTest(unittest.TestCase):
    """Giro completo tra formati: le variabili tornano identiche."""

    def test_v2_classico_v2(self) -> None:
        db = formats.load(copy.deepcopy(v2_doc())).db
        out, _ = formats.render(db, schema.CLASSIC, keep_variable_visibility=True)
        back, _ = formats.render(formats.load(out).db, schema.V2,
                                 keep_variable_visibility=True)
        self.assertEqual(v2_list(back), v2_list(v2_doc()))

    def test_classico_v2_classico(self) -> None:
        originale = classic_with_variables()
        db = formats.load(copy.deepcopy(originale)).db
        out, _ = formats.render(db, schema.V2, keep_variable_visibility=True)
        back, _ = formats.render(formats.load(out).db, schema.CLASSIC,
                                 keep_variable_visibility=True)
        self.assertEqual(classic_list(back), classic_list(originale))

    def test_query_in_forma_di_stringa(self) -> None:
        """La forma classica della query non cambia con il giro."""
        originale = {
            "name": "x", "type": "query", "query": "label_values(up)",
            "datasource": {"type": "prometheus", "uid": "p1"},
        }
        doc = {"title": "T", "panels": [], "templating": {"list": [originale]}}
        v2, _ = formats.render(formats.load(copy.deepcopy(doc)).db, schema.V2,
                               keep_variable_visibility=True)
        back, _ = formats.render(formats.load(v2).db, schema.CLASSIC,
                                 keep_variable_visibility=True)
        self.assertEqual(classic_list(back), [originale])

    def test_query_in_forma_di_oggetto(self) -> None:
        originale = {
            "name": "x", "type": "query",
            "query": {"query": "label_values(up)", "refId": "A"},
            "datasource": {"type": "prometheus", "uid": "p1"},
        }
        doc = {"title": "T", "panels": [], "templating": {"list": [originale]}}
        v2, _ = formats.render(formats.load(copy.deepcopy(doc)).db, schema.V2,
                               keep_variable_visibility=True)
        back, _ = formats.render(formats.load(v2).db, schema.CLASSIC,
                                 keep_variable_visibility=True)
        self.assertEqual(classic_list(back), [originale])


class SubstitutionTest(unittest.TestCase):
    """Regola 2: i valori fissi che hanno il nome di una variabile diventano `$var`."""

    @staticmethod
    def _dashboard(expr: str, tipo: str = "query", nome: str = "cluster_gen") -> dict:
        db = sample_dashboard()
        db["templating"] = {"list": [{"name": nome, "type": tipo, "query": "x"}]}
        db["panels"].append({
            "id": 200, "type": "timeseries", "title": "Prova",
            "gridPos": {"h": 8, "w": 12, "x": 0, "y": 0},
            "targets": [{"refId": "A", "expr": expr}],
        })
        return db

    @staticmethod
    def _expr(db: dict) -> str:
        for _, _, panel, _ in model.iter_panel_slots(db):
            if panel.get("id") == 200:
                return panel["targets"][0]["expr"]
        raise AssertionError("pannello di prova assente")

    def test_valore_fisso_sostituito(self) -> None:
        out, report = formats.render(self._dashboard('m{cluster_gen="3"}'), schema.CLASSIC)
        self.assertEqual(self._expr(out), 'm{cluster_gen="$cluster_gen"}')
        self.assertTrue(any("$cluster_gen" in message for _, message in report.entries))

    def test_valore_gia_variabile_lasciato(self) -> None:
        out, _ = formats.render(
            self._dashboard('m{cluster_gen="$cluster_gen"}'), schema.CLASSIC
        )
        self.assertEqual(self._expr(out), 'm{cluster_gen="$cluster_gen"}')

    def test_operatori_diversi(self) -> None:
        for op in ("=", "=~", "!=", "!~"):
            out, _ = formats.render(self._dashboard(f'm{{cluster_gen{op}"3"}}'),
                                    schema.CLASSIC)
            self.assertEqual(self._expr(out), f'm{{cluster_gen{op}"$cluster_gen"}}')

    def test_etichetta_senza_variabile_lasciata(self) -> None:
        out, _ = formats.render(self._dashboard('m{namespace="nesb"}'), schema.CLASSIC)
        self.assertEqual(self._expr(out), 'm{namespace="nesb"}')

    def test_valore_vuoto_lasciato(self) -> None:
        out, _ = formats.render(self._dashboard('m{cluster_gen=""}'), schema.CLASSIC)
        self.assertEqual(self._expr(out), 'm{cluster_gen=""}')

    def test_variabile_datasource_non_sostituisce(self) -> None:
        """`env` è un datasource: non è un valore di matcher."""
        out, _ = formats.render(
            self._dashboard('m{env="3"}', tipo="datasource", nome="env"), schema.CLASSIC
        )
        self.assertEqual(self._expr(out), 'm{env="3"}')

    def test_keep_literal_values(self) -> None:
        out, report = formats.render(
            self._dashboard('m{cluster_gen="3"}'), schema.CLASSIC,
            keep_literal_values=True,
        )
        self.assertEqual(self._expr(out), 'm{cluster_gen="3"}')
        self.assertFalse(any("sostituiti" in message for _, message in report.entries))

    def test_rewrite_multiple_occorrenze(self) -> None:
        scritto, trovate = variables_module._rewrite_expression(
            'a{cluster_gen="1"} + b{cluster_gen="2"}', {"cluster_gen"}
        )
        self.assertEqual(
            scritto, 'a{cluster_gen="$cluster_gen"} + b{cluster_gen="$cluster_gen"}'
        )
        self.assertEqual(trovate, {"cluster_gen": 2})


class ExtractTest(CLITestCase):
    """`extract` eredita le variabili: è una scelta, non una svista."""

    def test_estrazione_conserva_le_variabili(self) -> None:
        src = self.write_json("in.json", classic_with_variables())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli("extract", "panel", "--id", "2", src, "-o", out)
        self.assertEqual(code, 0, stdout)
        self.assertEqual(
            without_hide(classic_list(self.read_json(out))),
            without_hide(classic_list(classic_with_variables())),
        )


class LiteralScanTest(CLITestCase):
    """Sul file reale: nessun valore fisso resta dove esiste una variabile."""

    def test_nessun_literale_cluster_gen(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, err = self.run_cli(
            "fork", str(V2_FIXTURE), "--to-format", "classic", "-o", out
        )
        self.assertEqual(code, 0, stdout + err)
        testo = json.dumps(self.read_json(out))
        self.assertIsNone(LITERALE.search(testo), "restano matcher con valore fisso")


if __name__ == "__main__":
    unittest.main()
