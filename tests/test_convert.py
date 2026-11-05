"""Test della conversione tra JSON model classico e schema v2.

Coprono i due versi (v2 → canonico, canonico → v2), i round-trip, le guardie
sulle conversioni impossibili e il comportamento della CLI.
"""
from __future__ import annotations

import copy
import json
import unittest
from pathlib import Path

from grafana_tool import formats, model, schema
from grafana_tool.io import InputError

from support import CLITestCase, sample_dashboard

FIXTURES = Path(__file__).resolve().parent / "fixtures"
V2_FIXTURE = FIXTURES / "dashboard-v2.json"


def v2_fixture() -> dict:
    return json.loads(V2_FIXTURE.read_text(encoding="utf-8"))


def canonical_v2() -> dict:
    return formats.load(v2_fixture()).db


def projection(db: dict) -> dict:
    """Vista stabile della dashboard, indipendente da id e ordine delle chiavi.

    Le righe senza titolo sono quelle sintetiche in cui finiscono i pannelli
    che nel classico stavano fuori da ogni riga: vengono confrontate a parte.
    """
    contenuti = [
        (p.get("id"), p.get("title"), p.get("type"),
         tuple(sorted((p.get("gridPos") or {}).items())))
        for _, _, p, _ in model.iter_panel_slots(db)
    ]
    righe = [
        (row.get("title"), bool(row.get("collapsed")))
        for row in model.iter_rows(db)
        if row.get("title")
    ]
    return {
        "title": db.get("title"),
        "tags": db.get("tags") or [],
        "tabs": [t["title"] for t in schema.canonical_tabs(db)],
        "rows": righe,
        "panels": sorted(contenuti, key=lambda c: (c[0] is None, c[0])),
        "variables": (db.get("templating") or {}).get("list"),
        "time": db.get("time"),
        "timezone": db.get("timezone"),
        "refresh": db.get("refresh") or "",
    }


class ReadV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.db = canonical_v2()

    def test_tab(self) -> None:
        self.assertEqual(
            [t["title"] for t in schema.canonical_tabs(self.db)],
            ["Applicativa", "Sistemistica"],
        )

    def test_righe_e_gerarchia(self) -> None:
        righe = [(r.get("title"), r.get("collapsed")) for r in model.iter_rows(self.db)]
        self.assertEqual(righe, [("Generale", False), ("Infra", True)])

    def test_riga_espansa_ha_i_figli_top_level(self) -> None:
        generica = model.find_row(self.db, model.iter_rows(self.db).__next__()["id"])
        self.assertIsNotNone(generica)
        self.assertEqual([p["title"] for p in model.row_children(self.db, generica)],
                         ["Traffico", "Note"])

    def test_riga_collassata_annida_i_figli(self) -> None:
        infra = [r for r in model.iter_rows(self.db) if r.get("title") == "Infra"][0]
        self.assertEqual([p["title"] for p in infra["panels"]], ["Nodi attivi"])

    def test_grid_pos(self) -> None:
        traffico = [p for _, _, p, _ in model.iter_panel_slots(self.db)
                    if p.get("title") == "Traffico"][0]
        self.assertEqual(traffico["gridPos"], {"x": 0, "y": 0, "w": 16, "h": 8})

    def test_tipo_viz(self) -> None:
        tipi = {p["title"]: p["type"] for _, _, p, _ in model.iter_panel_slots(self.db)}
        self.assertEqual(tipi, {"Traffico": "timeseries", "Note": "text",
                                "Nodi attivi": "stat"})

    def test_query(self) -> None:
        traffico = [p for _, _, p, _ in model.iter_panel_slots(self.db)
                    if p.get("title") == "Traffico"][0]
        self.assertEqual([t["refId"] for t in traffico["targets"]], ["A", "B"])
        primo = traffico["targets"][0]
        self.assertEqual(primo["expr"], "sum(rate(http_requests_total[5m]))")
        self.assertEqual(primo["datasource"], {"type": "prometheus", "uid": "prom-main"})
        self.assertNotIn("hide", primo)
        self.assertTrue(traffico["targets"][1]["hide"])

    def test_blocchi_accanto_ai_target(self) -> None:
        traffico = [p for _, _, p, _ in model.iter_panel_slots(self.db)
                    if p.get("title") == "Traffico"][0]
        self.assertEqual(traffico["queryOptions"], {"interval": "1m"})
        self.assertEqual(traffico["transformations"],
                         [{"id": "organize", "options": {"excludeByName": {"Time": True}}}])

    def test_fedelta_del_pannello(self) -> None:
        traffico = [p for _, _, p, _ in model.iter_panel_slots(self.db)
                    if p.get("title") == "Traffico"][0]
        self.assertTrue(traffico["transparent"])
        self.assertEqual(traffico["description"], "Richiesta al secondo")
        self.assertEqual(
            traffico["fieldConfig"]["overrides"][0]["matcher"],
            {"id": "byName", "options": "errori"},
        )

    def test_tempo(self) -> None:
        self.assertEqual(self.db["time"], {"from": "now-3h", "to": "now"})
        self.assertEqual(self.db["timezone"], "browser")
        self.assertEqual(self.db["refresh"], "1m")
        self.assertEqual(self.db["timepicker"],
                         {"refresh_intervals": ["30s", "1m", "5m"], "hidden": False})

    def test_variabili(self) -> None:
        variabili = self.db["templating"]["list"]
        self.assertEqual([v["type"] for v in variabili], ["datasource", "query"])
        self.assertEqual(variabili[0]["query"], "prometheus")
        self.assertEqual(variabili[1]["datasource"],
                         {"type": "prometheus", "uid": "prom-main"})
        self.assertEqual(variabili[1]["query"]["query"], "label_values(cluster_gen)")

    def test_annotazioni(self) -> None:
        ann = self.db["annotations"]["list"][0]
        self.assertEqual(ann["name"], "Annotations & Alerts")
        self.assertEqual(ann["datasource"], {"type": "grafana", "uid": "grafana"})
        self.assertEqual(ann["type"], "dashboard")

    def test_link_e_extra(self) -> None:
        self.assertEqual(self.db["links"][0]["title"], "Runbook")
        self.assertEqual(self.db["_extras"], {"cursorSync": "Off", "preload": False,
                                              "liveNow": False})

    def test_nessuna_chiave_interna_nel_classico(self) -> None:
        db = formats.load(self._un_tab()).db
        out, _ = formats.render(db, schema.CLASSIC)
        testo = json.dumps(out)
        for chiave in ("_tabs", "_tab", "_element", "_extras"):
            self.assertNotIn(f'"{chiave}"', testo)

    @staticmethod
    def _un_tab() -> dict:
        """La fixture ridotta a un tab: l'unica forma scrivibile in classico."""
        raw = v2_fixture()
        raw["layout"]["spec"]["tabs"] = raw["layout"]["spec"]["tabs"][:1]
        del raw["elements"]["panel-3"]
        return raw


class WriteV2Test(unittest.TestCase):
    def setUp(self) -> None:
        self.db = canonical_v2()

    def test_struttura(self) -> None:
        out, _ = formats.render(self.db, schema.V2)
        self.assertEqual(out["layout"]["kind"], "TabsLayout")
        self.assertEqual(len(out["layout"]["spec"]["tabs"]), 2)
        self.assertEqual(sorted(out["elements"]), ["panel-1", "panel-2", "panel-3"])

    def test_nomi_elemento_conservati(self) -> None:
        out, _ = formats.render(self.db, schema.V2)
        self.assertEqual(out["elements"]["panel-1"]["spec"]["title"], "Traffico")

    def test_query_ricostruite(self) -> None:
        out, _ = formats.render(self.db, schema.V2)
        query = out["elements"]["panel-1"]["spec"]["data"]["spec"]["queries"]
        self.assertEqual([q["spec"]["refId"] for q in query], ["A", "B"])
        self.assertTrue(query[1]["spec"]["hidden"])
        self.assertEqual(query[0]["spec"]["query"]["datasource"], {"name": "prom-main"})
        self.assertEqual(query[0]["spec"]["query"]["group"], "prometheus")
        self.assertEqual(query[0]["spec"]["query"]["spec"]["expr"],
                         "sum(rate(http_requests_total[5m]))")

    def test_collapse_preservato(self) -> None:
        out, _ = formats.render(self.db, schema.V2)
        righe = out["layout"]["spec"]["tabs"][0]["spec"]["layout"]["spec"]["rows"]
        self.assertFalse(righe[0]["spec"]["collapse"])

    def test_uid_id_version_dichiarati_come_perdita(self) -> None:
        db = copy.deepcopy(self.db)
        db.update({"uid": "abc", "id": 7, "version": 3})
        out, report = formats.render(db, schema.V2)
        self.assertNotIn("uid", out)
        self.assertTrue(any("uid" in message for _, message in report.entries))


class RoundTripTest(unittest.TestCase):
    def test_v2_riscritto_e_identico(self) -> None:
        prima = canonical_v2()
        v2a, _ = formats.render(prima, schema.V2)
        seconda = formats.read_v2(v2a)[0]
        v2b, _ = formats.render(seconda, schema.V2)
        self.assertEqual(v2a, v2b)
        self.assertEqual(projection(prima), projection(seconda))

    def test_classico_v2_classico(self) -> None:
        originale = sample_dashboard()
        canonico = formats.load(copy.deepcopy(originale)).db
        v2, _ = formats.render(canonico, schema.V2)
        indietro = formats.load(v2).db
        self.assertEqual(projection(formats.load(copy.deepcopy(originale)).db),
                         projection(indietro))

    def test_pannello_fuori_riga_finisce_in_una_riga(self) -> None:
        canonico = formats.load(sample_dashboard()).db
        v2, _ = formats.render(canonico, schema.V2)
        indietro = formats.load(v2).db
        ids = {p["id"] for _, _, p, _ in model.iter_panel_slots(indietro)}
        self.assertIn(100, ids)


class GuardTest(unittest.TestCase):
    def _v2_condue_tab(self) -> dict:
        raw = v2_fixture()
        raw["layout"]["spec"]["tabs"] = raw["layout"]["spec"]["tabs"][:1]
        del raw["elements"]["panel-3"]
        return raw

    def test_due_tab_vengono_appiattiti_in_una_vista(self) -> None:
        db = canonical_v2()
        out, report = formats.render(db, schema.CLASSIC)
        righe = [p for p in out["panels"] if p.get("type") == "row"]
        self.assertEqual(
            [r["title"] for r in righe],
            ["Applicativa-Generale", "Sistemistica-Infra"],
        )
        self.assertTrue(any("prefisso" in message for _, message in report.entries))

    def test_un_tab_in_uscita_classica_e_ammesso(self) -> None:
        db = formats.load(self._v2_condue_tab()).db
        out, _ = formats.render(db, schema.CLASSIC)
        contenuti = [p for p in out["panels"] if p.get("type") != "row"]
        self.assertEqual(len(contenuti), 2)

    def test_classico_senza_identita_lo_dichiara(self) -> None:
        """Da v2 il file classico esce senza uid/id/version: va detto."""
        db = formats.load(self._v2_condue_tab()).db
        _, report = formats.render(db, schema.CLASSIC)
        self.assertTrue(
            any("uid" in message and "Grafana" in message
                for _, message in report.entries)
        )

    def test_classico_con_identita_non_dice_nulla(self) -> None:
        db = formats.load(self._v2_condue_tab()).db
        db.update({"uid": "abc", "id": 3, "version": 5})
        _, report = formats.render(db, schema.CLASSIC)
        messaggi = [message for _, message in report.entries]
        self.assertFalse(any("uid" in message for message in messaggi))

    def test_elemento_in_due_posizioni_e_un_errore(self) -> None:
        raw = v2_fixture()
        items = raw["layout"]["spec"]["tabs"][1]["spec"]["layout"]["spec"]["rows"][0][
            "spec"]["layout"]["spec"]["items"]
        items[0]["spec"]["element"]["name"] = "panel-1"
        with self.assertRaises(InputError) as ctx:
            formats.load(raw)
        self.assertIn("panel-1", str(ctx.exception))

    def test_elemento_non_collocato_viene_dichiarato(self) -> None:
        raw = v2_fixture()
        raw["elements"]["panel-99"] = raw["elements"]["panel-2"]
        loaded = formats.load(raw)
        self.assertTrue(any("panel-99" in m for _, m in loaded.report.entries))

    def test_alert_legacy_bloccano_l_uscita_v2(self) -> None:
        db = canonical_v2()
        primo = next(p for _, _, p, _ in model.iter_panel_slots(db))
        primo["alert"] = {"name": "vecchio"}
        with self.assertRaises(InputError) as ctx:
            formats.render(db, schema.V2)
        self.assertIn("--drop-alerts", str(ctx.exception))

    def test_drop_alerts_permette_l_uscita(self) -> None:
        db = canonical_v2()
        primo = next(p for _, _, p, _ in model.iter_panel_slots(db))
        primo["alert"] = {"name": "vecchio"}
        out, _ = formats.render(db, schema.V2, drop_alerts=True)
        self.assertIn("elements", out)


class CLIConversionTest(CLITestCase):
    def test_formato_sconosciuto_esce_con_2_e_non_scrive(self) -> None:
        src = self.write_json("strano.json", {"title": "x"})
        out = str(self.tmp / "out.json")
        code, _, err = self.run_cli(
            "update", "panel", "--id", "1", "--title", "X", src, "-o", out
        )
        self.assertEqual(code, 2)
        self.assertIn("formato non riconosciuto", err)
        self.assertFalse(Path(out).exists())

    def test_v2_in_ingresso_resta_v2_in_uscita(self) -> None:
        out = str(self.tmp / "out.json")
        code, stdout, _ = self.run_cli(
            "update", "panel", "--id", "1", "--title", "Traffico 2",
            str(V2_FIXTURE), "-o", out,
        )
        self.assertEqual(code, 0, stdout)
        scritto = self.read_json(out)
        self.assertIn("elements", scritto)
        self.assertIn("layout", scritto)
        self.assertEqual(scritto["elements"]["panel-1"]["spec"]["title"], "Traffico 2")

    def test_to_format_converte_un_tab_in_classico(self) -> None:
        raw = v2_fixture()
        raw["layout"]["spec"]["tabs"] = raw["layout"]["spec"]["tabs"][:1]
        del raw["elements"]["panel-3"]
        src = self.write_json("v2unatab.json", raw)
        out = str(self.tmp / "classico.json")
        code, stdout, _ = self.run_cli(
            "update", "panel", "--id", "1", "--title", "Traffico 2",
            src, "-o", out, "--to-format", "classic",
        )
        self.assertEqual(code, 0, stdout)
        scritto = self.read_json(out)
        self.assertIn("panels", scritto)
        self.assertNotIn("elements", scritto)

    def test_due_tab_in_classico_diventano_una_vista(self) -> None:
        out = str(self.tmp / "classico.json")
        code, stdout, err = self.run_cli(
            "update", "panel", "--id", "1", "--title", "X",
            str(V2_FIXTURE), "-o", out, "--to-format", "classic",
        )
        self.assertEqual(code, 0, stdout + err)
        scritto = self.read_json(out)
        righe = [p["title"] for p in scritto["panels"] if p.get("type") == "row"]
        self.assertEqual(righe, ["Applicativa-Generale", "Sistemistica-Infra"])

    def test_file_di_input_non_viene_modificato(self) -> None:
        prima = V2_FIXTURE.read_text(encoding="utf-8")
        self.run_cli("update", "panel", "--id", "1", "--title", "X",
                     str(V2_FIXTURE), "-o", str(self.tmp / "out.json"))
        self.assertEqual(prima, V2_FIXTURE.read_text(encoding="utf-8"))


class PurityTest(unittest.TestCase):
    """Fuori da `schema.py` e `formats/` il formato non deve trapelare."""

    def test_nessun_comando_conosce_elements_o_layout(self) -> None:
        root = Path(__file__).resolve().parent.parent / "grafana_tool"
        colpevoli = []
        for path in root.rglob("*.py"):
            rel = path.relative_to(root)
            if rel == Path("schema.py") or rel.parts[0] == "formats":
                continue
            testo = path.read_text(encoding="utf-8")
            for marcatore in ('["elements"]', '.get("elements")', '["layout"]',
                              '.get("layout")'):
                if marcatore in testo:
                    colpevoli.append(f"{rel}: {marcatore}")
        self.assertEqual(colpevoli, [])


if __name__ == "__main__":
    unittest.main()
