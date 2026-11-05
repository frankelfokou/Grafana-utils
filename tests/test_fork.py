"""Test di `fork`: copia integrale senza identità né vincoli della sorgente."""
from __future__ import annotations

import json
import unittest
from pathlib import Path

from grafana_tool import model

from tests.support import CLITestCase, panel, row, sample_dashboard

FIXTURES = Path(__file__).resolve().parent / "fixtures"
V2_FIXTURE = FIXTURES / "dashboard-v2.json"


def bound_dashboard() -> dict:
    """Dashboard con tutti i vincoli che un fork deve staccare."""
    libreria = panel(20, "Da libreria")
    libreria["libraryPanel"] = {"uid": "lib-1", "name": "Riquadro condiviso"}
    con_alert = panel(21, "Con alert")
    con_alert["alert"] = {"name": "Troppi errori", "conditions": []}
    con_alert["alertId"] = 7

    db = sample_dashboard()
    db["uid"] = "sorgente01"
    db["id"] = 42
    db["version"] = 9
    db["title"] = "Sorgente"
    db["links"] = [{"title": "Runbook", "url": "https://example.invalid", "type": "link"}]
    db["panels"].extend([
        row(30, "Vincoli", collapsed=True, panels=[libreria, con_alert]),
    ])
    return db


class ForkClassicTest(CLITestCase):
    def _fork(self, *extra: str, source: dict | None = None) -> dict:
        src = self.write_json("in.json", source or bound_dashboard())
        out = self.tmp / "out.json"
        code, stdout, err = self.run_cli("fork", src, "-o", out, *extra)
        self.assertEqual(code, 0, stdout + err)
        return self.read_json(out)

    def test_identita_nuova(self) -> None:
        scritto = self._fork()
        self.assertNotEqual(scritto["uid"], "sorgente01")
        self.assertIsNone(scritto["id"])
        self.assertEqual(scritto["version"], 1)

    def test_titolo_reso_unico(self) -> None:
        self.assertEqual(self._fork()["title"], "Sorgente (2)")

    def test_titolo_esplicito(self) -> None:
        self.assertEqual(self._fork("--title", "Copia")["title"], "Copia")

    def test_id_rinumerati_da_uno(self) -> None:
        scritto = self._fork()
        ids = [p["id"] for p in model.iter_all_panels(scritto)]
        self.assertEqual(ids[0], 1)
        self.assertEqual(len(ids), len(set(ids)))
        self.assertEqual(sorted(ids), list(range(1, len(ids) + 1)))

    def test_libreria_staccata(self) -> None:
        scritto = self._fork()
        con_libreria = [p for p in model.iter_all_panels(scritto)
                        if p.get("title") == "Da libreria"]
        self.assertEqual(len(con_libreria), 1)
        self.assertNotIn("libraryPanel", con_libreria[0])

    def test_alert_rimossi(self) -> None:
        scritto = self._fork()
        con_alert = [p for p in model.iter_all_panels(scritto)
                     if p.get("title") == "Con alert"][0]
        self.assertNotIn("alert", con_alert)
        self.assertNotIn("alertId", con_alert)

    def test_link_conservati(self) -> None:
        self.assertEqual(len(self._fork()["links"]), 1)

    def test_strip_links(self) -> None:
        self.assertEqual(self._fork("--strip-links")["links"], [])

    def test_keep_library(self) -> None:
        scritto = self._fork("--keep-library")
        con_libreria = [p for p in model.iter_all_panels(scritto)
                        if p.get("title") == "Da libreria"][0]
        self.assertIn("libraryPanel", con_libreria)

    def test_keep_alerts(self) -> None:
        scritto = self._fork("--keep-alerts")
        con_alert = [p for p in model.iter_all_panels(scritto)
                     if p.get("title") == "Con alert"][0]
        self.assertIn("alert", con_alert)

    def test_uid_esplicito(self) -> None:
        self.assertEqual(self._fork("--uid", "nuovo123")["uid"], "nuovo123")

    def test_uid_gia_in_inventario(self) -> None:
        inventario = self.write_json("inv.json", [{"uid": "occupato", "title": "X"}])
        src = self.write_json("in.json", bound_dashboard())
        out = self.tmp / "out.json"
        code, _, err = self.run_cli(
            "fork", src, "-o", out, "--uid", "occupato",
            "--existing-dashboards", inventario,
        )
        self.assertEqual(code, 1)
        self.assertIn("già usato", err)
        self.assertFalse(out.exists())

    def test_uid_della_sorgente_non_si_riusa(self) -> None:
        inventario = self.write_json("inv.json", [{"uid": "sorgente01", "title": "X"}])
        src = self.write_json("in.json", bound_dashboard())
        out = self.tmp / "out.json"
        code, _, err = self.run_cli(
            "fork", src, "-o", out, "--uid", "sorgente01",
            "--existing-dashboards", inventario,
        )
        self.assertEqual(code, 1)
        self.assertIn("già usato", err)

    def test_titolo_dell_inventario_non_si_riusa(self) -> None:
        inventario = self.write_json("inv.json", [{"uid": "altro", "title": "Sorgente"}])
        src = self.write_json("in.json", bound_dashboard())
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "fork", src, "-o", out, "--existing-dashboards", inventario
        )
        self.assertEqual(code, 0, stdout)
        self.assertEqual(self.read_json(out)["title"], "Sorgente (2)")

    def test_contenuto_invariato(self) -> None:
        scritto = self._fork()
        titoli_prima = sorted(p.get("title") for p in model.iter_all_panels(bound_dashboard()))
        titoli_dopo = sorted(p.get("title") for p in model.iter_all_panels(scritto))
        self.assertEqual(titoli_prima, titoli_dopo)


class ForkFormatsTest(CLITestCase):
    def test_da_v2_a_v2(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, err = self.run_cli("fork", str(V2_FIXTURE), "-o", out)
        self.assertEqual(code, 0, stdout + err)
        scritto = self.read_json(out)
        self.assertIn("elements", scritto)
        self.assertNotIn("uid", scritto)
        self.assertIsNone(scritto.get("id"))
        self.assertEqual(
            [t["spec"]["title"] for t in scritto["layout"]["spec"]["tabs"]],
            ["Applicativa", "Sistemistica"],
        )
        self.assertEqual(scritto["title"], "Dashboard v2 di prova (2)")

    def test_elementi_rinominati_coi_nuovi_id(self) -> None:
        out = self.tmp / "out.json"
        self.run_cli("fork", str(V2_FIXTURE), "-o", out)
        scritto = self.read_json(out)
        for name, element in scritto["elements"].items():
            self.assertEqual(name, f"panel-{element['spec']['id']}")

    def test_da_v2_a_classico_assegna_uid(self) -> None:
        raw = json.loads(V2_FIXTURE.read_text(encoding="utf-8"))
        raw["layout"]["spec"]["tabs"] = raw["layout"]["spec"]["tabs"][:1]
        del raw["elements"]["panel-3"]
        src = self.write_json("uno.json", raw)
        out = self.tmp / "out.json"
        code, stdout, err = self.run_cli(
            "fork", src, "-o", out, "--to-format", "classic"
        )
        self.assertEqual(code, 0, stdout + err)
        scritto = self.read_json(out)
        self.assertIn("panels", scritto)
        self.assertTrue(scritto["uid"])
        self.assertIsNone(scritto["id"])

    def test_uid_rifiutato_con_uscita_v2(self) -> None:
        out = self.tmp / "out.json"
        code, _, err = self.run_cli(
            "fork", str(V2_FIXTURE), "-o", out, "--uid", "abc123"
        )
        self.assertEqual(code, 1)
        self.assertIn("--uid non ha effetto con l'uscita v2", err)
        self.assertFalse(out.exists())


class ForkKeepTabTest(CLITestCase):
    """Un solo comando per duplicare una dashboard a più tab come classico."""

    def test_da_due_tab_a_classico(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, err = self.run_cli(
            "fork", str(V2_FIXTURE), "--keep-tab", "2", "--to-format", "classic",
            "-o", out,
        )
        self.assertEqual(code, 0, stdout + err)
        scritto = self.read_json(out)
        self.assertIn("panels", scritto)
        self.assertNotIn("elements", scritto)
        self.assertTrue(scritto["uid"])
        self.assertIsNone(scritto["id"])
        self.assertEqual(scritto["version"], 1)

    def test_tiene_solo_il_tab_indicato(self) -> None:
        out = self.tmp / "out.json"
        self.run_cli(
            "fork", str(V2_FIXTURE), "--keep-tab", "2", "--to-format", "classic",
            "-o", out,
        )
        scritto = self.read_json(out)
        righe = [p for p in model.iter_rows(scritto)]
        self.assertEqual([r["title"] for r in righe], ["Infra"])
        self.assertEqual(
            [p["id"] for _, _, p, _ in model.iter_panel_slots(scritto)],
            [1],
        )

    def test_scarto_dichiarato(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "fork", str(V2_FIXTURE), "--keep-tab", "2", "-o", out
        )
        self.assertEqual(code, 0)
        self.assertIn("scartati gli altri con 2 pannelli", stdout)

    def test_uscita_v2_con_un_solo_tab(self) -> None:
        out = self.tmp / "out.json"
        code, stdout, _ = self.run_cli(
            "fork", str(V2_FIXTURE), "--keep-tab", "1", "-o", out
        )
        self.assertEqual(code, 0, stdout)
        scritto = self.read_json(out)
        self.assertEqual(
            [t["spec"]["title"] for t in scritto["layout"]["spec"]["tabs"]],
            ["Applicativa"],
        )
        self.assertEqual(sorted(scritto["elements"]), ["panel-1", "panel-2"])

    def test_tab_inesistente(self) -> None:
        out = self.tmp / "out.json"
        code, _, err = self.run_cli(
            "fork", str(V2_FIXTURE), "--keep-tab", "99", "-o", out
        )
        self.assertEqual(code, 1)
        self.assertIn("Tab 99 non trovato", err)
        self.assertIn("Applicativa", err)
        self.assertFalse(out.exists())

    def test_conserva_variabili_e_tempo(self) -> None:
        out = self.tmp / "out.json"
        self.run_cli(
            "fork", str(V2_FIXTURE), "--keep-tab", "2", "--to-format", "classic",
            "-o", out,
        )
        scritto = self.read_json(out)
        self.assertEqual(
            [v["name"] for v in scritto["templating"]["list"]],
            ["env", "cluster_gen"],
        )
        self.assertEqual(scritto["time"], {"from": "now-3h", "to": "now"})


if __name__ == "__main__":
    unittest.main()
