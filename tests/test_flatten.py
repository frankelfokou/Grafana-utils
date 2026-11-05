"""Test dell'appiattimento dei tab in un'unica vista classica."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from grafana_tool import formats, model, schema
from grafana_tool.formats import flatten as flatten_module

FIXTURES = Path(__file__).resolve().parent / "fixtures"
V2_FIXTURE = FIXTURES / "dashboard-v2.json"


def canonical() -> dict:
    return formats.load(json.loads(V2_FIXTURE.read_text(encoding="utf-8"))).db


def rows_of(db: dict) -> list[dict]:
    return list(model.iter_rows(db))


class SingleTabTest(unittest.TestCase):
    """Con un solo tab non c'è niente da appiattire: non si tocca nulla."""

    def test_nessuna_rinomina(self) -> None:
        db = canonical()
        db["_tabs"] = db["_tabs"][:1]
        for row in rows_of(db):
            row["_tab"] = db["_tabs"][0]["id"]
        esito = flatten_module.flatten(db)
        self.assertEqual(esito.renames, [])
        self.assertEqual(esito.moved_orphans, 0)

    def test_titoli_intatti(self) -> None:
        db = canonical()
        db["_tabs"] = db["_tabs"][:1]
        row = rows_of(db)[0]
        row["_tab"] = db["_tabs"][0]["id"]
        prima = row["title"]
        flatten_module.flatten(db)
        self.assertEqual(row["title"], prima)


class MultiTabTest(unittest.TestCase):
    def setUp(self) -> None:
        self.db = canonical()
        esito = flatten_module.flatten(self.db)
        self.renames = esito.renames
        self.moved = esito.moved_orphans

    def test_resta_un_solo_tab(self) -> None:
        self.assertEqual(len(schema.canonical_tabs(self.db)), 1)

    def test_prefisso_su_ogni_riga(self) -> None:
        self.assertEqual(
            [row["title"] for row in rows_of(self.db)],
            ["Applicativa-Generale", "Sistemistica-Infra"],
        )

    def test_righe_ordinate_per_tab(self) -> None:
        """Le righe del primo tab vengono prima di quelle del secondo."""
        tab = schema.canonical_tabs(self.db)[0]["id"]
        self.assertTrue(all(row["_tab"] == tab for row in rows_of(self.db)))

    def test_rinomine_riportate(self) -> None:
        self.assertEqual(
            [(r.kind, r.before, r.after) for r in self.renames],
            [
                ("row", "Generale", "Applicativa-Generale"),
                ("row", "Infra", "Sistemistica-Infra"),
            ],
        )

    def test_righe_hanno_una_posizione(self) -> None:
        ys = [row["gridPos"]["y"] for row in rows_of(self.db)]
        self.assertEqual(ys, sorted(ys))
        self.assertEqual(len(set(ys)), len(ys))

    def test_figli_sotto_l_intestazione(self) -> None:
        for row in rows_of(self.db):
            for child in model.row_children(self.db, row):
                self.assertGreater(child["gridPos"]["y"], row["gridPos"]["y"])

    def test_nessuna_sovrapposizione(self) -> None:
        rettangoli = []
        for _, _, panel, _ in model.iter_panel_slots(self.db):
            grid = panel["gridPos"]
            rettangoli.append((grid["x"], grid["y"], grid["x"] + grid["w"],
                               grid["y"] + grid["h"]))
        for i, primo in enumerate(rettangoli):
            for secondo in rettangoli[i + 1:]:
                sovrapposti = (
                    primo[0] < secondo[2] and secondo[0] < primo[2]
                    and primo[1] < secondo[3] and secondo[1] < primo[3]
                )
                self.assertFalse(sovrapposti, f"{primo} / {secondo}")

    def test_contenuto_invariato(self) -> None:
        titoli = sorted(
            p["title"] for _, _, p, _ in model.iter_panel_slots(self.db)
        )
        self.assertEqual(titoli, ["Nodi attivi", "Note", "Traffico"])


class PrefixTest(unittest.TestCase):
    def test_formato(self) -> None:
        self.assertEqual(flatten_module.prefixed("Tab", "Riga"), "Tab-Riga")

    def test_titolo_vuoto(self) -> None:
        self.assertEqual(flatten_module.prefixed("Tab", ""), "Tab")

    def test_titolo_mancante(self) -> None:
        self.assertEqual(flatten_module.prefixed("Tab", None), "Tab")

    def test_prefisso_vuoto(self) -> None:
        self.assertEqual(flatten_module.prefixed("", "Riga"), "Riga")

    def test_spazi_ripuliti(self) -> None:
        self.assertEqual(flatten_module.prefixed(" Tab ", "  Riga  "), "Tab-Riga")


class OrphanTest(unittest.TestCase):
    def test_pannello_fuori_riga_prefissato_e_spostato(self) -> None:
        db = canonical()
        db["panels"].append(
            {"id": 99, "type": "text", "title": "Libero", "gridPos": {"x": 0, "y": 0, "w": 6, "h": 3}}
        )
        esito = flatten_module.flatten(db)
        self.assertEqual(esito.moved_orphans, 1)
        self.assertIn(("panel", "Libero", "Applicativa-Libero"),
                      [(r.kind, r.before, r.after) for r in esito.renames])

        libero = [p for _, _, p, _ in model.iter_panel_slots(db) if p["id"] == 99]
        self.assertEqual(len(libero), 1)
        self.assertEqual(libero[0]["title"], "Applicativa-Libero")

    def test_il_pannello_libero_finisce_in_fondo(self) -> None:
        db = canonical()
        db["panels"].append(
            {"id": 99, "type": "text", "title": "Libero", "gridPos": {"x": 0, "y": 0, "w": 6, "h": 3}}
        )
        flatten_module.flatten(db)
        ultimo = [p for p in db["panels"] if p.get("type") != "row"][-1]
        self.assertEqual(ultimo["id"], 99)


class RenderTest(unittest.TestCase):
    def test_uscita_classica_appiattisce(self) -> None:
        out, report = formats.render(canonical(), schema.CLASSIC)
        self.assertNotIn("elements", out)
        self.assertEqual(
            [r["title"] for r in out["panels"] if r.get("type") == "row"],
            ["Applicativa-Generale", "Sistemistica-Infra"],
        )
        self.assertTrue(any("prefisso" in message for _, message in report.entries))

    def test_il_canonico_non_viene_modificato(self) -> None:
        db = canonical()
        originali = [row["title"] for row in rows_of(db)]
        formats.render(db, schema.CLASSIC)
        self.assertEqual([row["title"] for row in rows_of(db)], originali)
        self.assertEqual(len(schema.canonical_tabs(db)), 2)


if __name__ == "__main__":
    unittest.main()
