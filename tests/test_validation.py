"""Test di `grafana_tool.validation`."""
from __future__ import annotations

import unittest

from grafana_tool.validation import (
    SEV_ORDER,
    Result,
    check,
    render,
    structural_errors,
    summary,
)
from grafana_tool.linter import Issue
from tests.support import panel, row


class StructuralErrorsTest(unittest.TestCase):
    def test_dashboard_valida(self):
        self.assertEqual(structural_errors({"panels": [panel(1, "a"), panel(2, "b")]}), [])

    def test_id_duplicati(self):
        errors = structural_errors({"panels": [panel(1, "a"), panel(1, "b")]})
        self.assertEqual(len(errors), 1)
        self.assertIn("duplicati", errors[0])

    def test_id_mancante(self):
        errors = structural_errors({"panels": [{"type": "text", "title": "x"}]})
        self.assertEqual(len(errors), 1)
        self.assertIn("senza campo 'id'", errors[0])

    def test_considera_anche_le_righe(self):
        db = {"panels": [row(1, "R", panels=[panel(2, "a")]), panel(2, "duplicato")]}
        self.assertTrue(structural_errors(db))


class CheckTest(unittest.TestCase):
    def test_dashboard_pulita(self):
        db = {"panels": [row(1, "R", collapsed=True, panels=[
            panel(2, "ok", typ="stat", fieldConfig={"defaults": {"unit": "short"}})
        ])]}
        result = check(db)
        self.assertFalse(result.failing)
        self.assertIsNone(result.kind)
        self.assertEqual(result.counts(), {"info": 0, "warning": 0, "error": 0})

    def test_errori_strutturali_hanno_priorita_sul_lint(self):
        db = {"panels": [panel(1), panel(1)]}  # duplicato + titolo mancante
        result = check(db)
        self.assertTrue(result.failing)
        self.assertEqual(result.kind, "validation")

    def test_lint_oltre_soglia(self):
        db = {"panels": [panel(1)]}  # MISSING_TITLE warning
        result = check(db, "warning")
        self.assertTrue(result.failing)
        self.assertEqual(result.kind, "lint")

    def test_lint_sotto_soglia_non_blocca(self):
        db = {"panels": [panel(1)]}
        result = check(db, "error")
        self.assertFalse(result.failing)
        self.assertTrue(result.issues)

    def test_blocking_filtra_per_severita(self):
        result = Result([], [Issue("A", "info", "i"), Issue("B", "warning", "w")], "warning")
        self.assertEqual([i.code for i in result.blocking], ["B"])

    def test_counts(self):
        result = Result([], [Issue("A", "info", "i"), Issue("B", "warning", "w"), Issue("C", "error", "e")])
        self.assertEqual(result.counts(), {"info": 1, "warning": 1, "error": 1})


class RenderTest(unittest.TestCase):
    def test_ok(self):
        lines = render(check({"panels": []}))
        self.assertIn("Validazione: nessun errore strutturale.", lines)
        self.assertTrue(any(line.startswith("Lint: 0 issue") for line in lines))

    def test_errori_strutturali(self):
        lines = render(check({"panels": [panel(1), panel(1)]}))
        self.assertIn("Validazione: FALLITA", lines)
        self.assertTrue(any("DUPLICATE_PANEL_ID" in line for line in lines))

    def test_show_all_false_mostra_solo_le_bloccanti(self):
        result = check({"panels": [panel(1)]}, "warning")
        lines = render(result, show_all=False)
        self.assertTrue(any("MISSING_TITLE" in line for line in lines))


class SummaryTest(unittest.TestCase):
    def test_conta_righe_e_pannelli_di_contenuto(self):
        db = {"panels": [row(1, "R", panels=[panel(2, "a")]), panel(3, "top")]}
        self.assertEqual(summary(db), "righe: 1, pannelli: 2")

    def test_dashboard_vuota(self):
        self.assertEqual(summary({}), "righe: 0, pannelli: 0")


class SeverityOrderTest(unittest.TestCase):
    def test_ordine(self):
        self.assertLess(SEV_ORDER["info"], SEV_ORDER["warning"])
        self.assertLess(SEV_ORDER["warning"], SEV_ORDER["error"])


if __name__ == "__main__":
    unittest.main()
