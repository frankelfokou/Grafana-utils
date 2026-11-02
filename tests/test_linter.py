"""Test di `grafana_tool.linter`: ogni regola, sia quando scatta sia quando tace."""
from __future__ import annotations

import unittest

from grafana_tool.linter import (
    DEFAULT_RULES,
    DuplicatePanelIdRule,
    DuplicateQueryRule,
    EmptyRowRule,
    Issue,
    MissingDatasourceRule,
    MissingPanelIdRule,
    MissingTargetsRule,
    MissingTitleRule,
    MissingUnitRule,
    SharedLibraryPanelRule,
    lint,
)
from tests.support import panel, row


def codes(db, rule_cls=None):
    if rule_cls is None:
        return [i.code for i in lint(db)]
    return [i.code for i in lint(db, [rule_cls()])]


class MissingPanelIdTest(unittest.TestCase):
    def test_scatta_senza_id(self):
        db = {"panels": [{"type": "text", "title": "x"}]}
        issues = list(MissingPanelIdRule().check(db))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "error")
        self.assertIn("senza id", issues[0].message)

    def test_non_scatta_con_id(self):
        self.assertEqual(list(MissingPanelIdRule().check({"panels": [panel(1, "x")]})), [])


class DuplicatePanelIdTest(unittest.TestCase):
    def test_scatta_su_id_ripetuto(self):
        db = {"panels": [panel(1, "a"), panel(1, "b")]}
        issues = list(DuplicatePanelIdRule().check(db))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].panel_id, 1)

    def test_scatta_anche_con_pannello_annidato(self):
        db = {"panels": [panel(1, "a", panels=[panel(1, "b")])]}
        self.assertEqual(len(list(DuplicatePanelIdRule().check(db))), 1)

    def test_non_scatta_con_id_unici(self):
        db = {"panels": [panel(1, "a"), panel(2, "b")]}
        self.assertEqual(list(DuplicatePanelIdRule().check(db)), [])


class MissingTitleTest(unittest.TestCase):
    def test_scatta_senza_titolo(self):
        issues = list(MissingTitleRule().check({"panels": [panel(1)]}))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "warning")

    def test_ignora_le_righe(self):
        db = {"panels": [row(1, "R")]}
        self.assertEqual(list(MissingTitleRule().check(db)), [])

    def test_titolo_vuoto_scatta(self):
        self.assertEqual(len(list(MissingTitleRule().check({"panels": [panel(1, "")]}))), 1)


class MissingTargetsTest(unittest.TestCase):
    def test_scatta_su_pannello_dati_senza_target(self):
        p = panel(1, "x")
        p.pop("targets")
        self.assertEqual(len(list(MissingTargetsRule().check({"panels": [p]}))), 1)

    def test_ignora_text_e_righe(self):
        p = panel(1, "x", typ="text")
        p.pop("targets")
        db = {"panels": [p, row(2, "R")]}
        self.assertEqual(list(MissingTargetsRule().check(db)), [])


class DuplicateQueryTest(unittest.TestCase):
    def test_scatta_su_expr_identica(self):
        a = panel(1, "a")
        b = panel(2, "b")
        b["targets"][0]["expr"] = a["targets"][0]["expr"]
        issues = list(DuplicateQueryRule().check({"panels": [a, b]}))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].panel_id, 1)

    def test_ignora_spazi_ai_bordi(self):
        a = panel(1, "a")
        b = panel(2, "b")
        b["targets"][0]["expr"] = "  " + a["targets"][0]["expr"] + "  "
        self.assertEqual(len(list(DuplicateQueryRule().check({"panels": [a, b]}))), 1)

    def test_non_scatta_su_expr_vuote(self):
        a = panel(1, "a")
        b = panel(2, "b")
        a["targets"][0]["expr"] = ""
        b["targets"][0]["expr"] = ""
        self.assertEqual(list(DuplicateQueryRule().check({"panels": [a, b]})), [])


class MissingDatasourceTest(unittest.TestCase):
    def test_scatta_senza_datasource(self):
        p = panel(1, "x")
        p.pop("datasource")
        p["targets"][0].pop("datasource")
        self.assertEqual(len(list(MissingDatasourceRule().check({"panels": [p]}))), 1)

    def test_tace_se_il_target_dichiara_il_datasource(self):
        p = panel(1, "x")
        p.pop("datasource")
        self.assertEqual(list(MissingDatasourceRule().check({"panels": [p]})), [])

    def test_ignora_pannelli_senza_target(self):
        p = panel(1, "x", typ="text")
        p.pop("targets")
        p.pop("datasource")
        self.assertEqual(list(MissingDatasourceRule().check({"panels": [p]})), [])


class EmptyRowTest(unittest.TestCase):
    def test_scatta_su_riga_vuota_non_collassata(self):
        db = {"panels": [row(1, "R", collapsed=False)]}
        issues = list(EmptyRowRule().check(db))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].row_id, 1)

    def test_tace_su_riga_vuota_collassata(self):
        self.assertEqual(list(EmptyRowRule().check({"panels": [row(1, "R", collapsed=True)]})), [])

    def test_tace_su_riga_espansa_con_fratelli(self):
        db = {"panels": [row(1, "R", collapsed=False), panel(2, "x")]}
        self.assertEqual(list(EmptyRowRule().check(db)), [])


class MissingUnitTest(unittest.TestCase):
    def test_scatta_su_numerico_senza_unita(self):
        issues = list(MissingUnitRule().check({"panels": [panel(1, "x", typ="stat")]}))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "info")

    def test_tace_con_fieldconfig_unit(self):
        p = panel(1, "x", typ="stat")
        p["fieldConfig"] = {"defaults": {"unit": "percent"}}
        self.assertEqual(list(MissingUnitRule().check({"panels": [p]})), [])

    def test_tace_con_yaxes_format(self):
        p = panel(1, "x", typ="graph")
        p["yaxes"] = [{"format": "short"}]
        self.assertEqual(list(MissingUnitRule().check({"panels": [p]})), [])

    def test_ignora_tipi_non_numerici(self):
        self.assertEqual(list(MissingUnitRule().check({"panels": [panel(1, "x", typ="table")]})), [])


class SharedLibraryPanelTest(unittest.TestCase):
    def test_scatta_su_library_panel(self):
        p = panel(1, "x")
        p["libraryPanel"] = {"uid": "lib-1", "name": "CPU"}
        issues = list(SharedLibraryPanelRule().check({"panels": [p]}))
        self.assertEqual(len(issues), 1)
        self.assertEqual(issues[0].severity, "info")
        self.assertIn("lib-1", issues[0].message)

    def test_tace_senza_library_panel(self):
        self.assertEqual(list(SharedLibraryPanelRule().check({"panels": [panel(1, "x")]})), [])


class EngineTest(unittest.TestCase):
    def test_default_rules_coprono_tutti_i_codici(self):
        self.assertEqual(
            sorted(r.code for r in DEFAULT_RULES),
            [
                "DUPLICATE_PANEL_ID",
                "DUPLICATE_QUERY",
                "EMPTY_ROW",
                "MISSING_DATASOURCE",
                "MISSING_PANEL_ID",
                "MISSING_TARGETS",
                "MISSING_TITLE",
                "MISSING_UNIT",
                "SHARED_LIBRARY_PANEL",
            ],
        )

    def test_regole_personalizzate(self):
        class AlwaysRule(MissingTitleRule):
            def check(self, db):
                yield Issue("X", "info", "sempre")

        self.assertEqual([i.code for i in lint({"panels": []}, [AlwaysRule()])], ["X"])

    def test_dashboard_pulita(self):
        db = {"panels": [row(1, "R", collapsed=True, panels=[panel(2, "ok", typ="stat",
                                                                   fieldConfig={"defaults": {"unit": "short"}})])]}
        self.assertEqual(lint(db), [])

    def test_issue_as_dict(self):
        i = Issue("C", "warning", "m", panel_id=3, row_id=4)
        self.assertEqual(i.as_dict(), {"code": "C", "severity": "warning", "message": "m",
                                       "panel_id": 3, "row_id": 4})
        self.assertEqual(Issue("C", "warning", "m").as_dict(), {"code": "C", "severity": "warning",
                                                                "message": "m"})


if __name__ == "__main__":
    unittest.main()
