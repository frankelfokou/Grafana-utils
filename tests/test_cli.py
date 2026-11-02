"""Test di `grafana_tool.cli`: parser, dispatch, exit code e log d'uso."""
from __future__ import annotations

import unittest

from grafana_tool import __version__, cli
from grafana_tool.commands import ALL_COMMANDS
from tests.support import CLITestCase, panel, sample_dashboard


class ParserTest(unittest.TestCase):
    def test_registra_tutti_i_comandi(self):
        parser = cli.build_parser()
        actions = [a for a in parser._actions if hasattr(a, "choices") and a.choices]
        subparsers = actions[-1].choices
        self.assertEqual(sorted(subparsers), sorted(c.NAME for c in ALL_COMMANDS))

    def test_comandi_attesi(self):
        names = {c.NAME for c in ALL_COMMANDS}
        self.assertEqual(
            names,
            {
                "list-rows", "list-panels", "duplicate-row", "copy-panel", "move-panel",
                "replace", "transform", "prune", "set-datasource", "reflow",
                "validate", "lint", "append-row", "extract-row",
            },
        )

    def test_parse_assegna_la_funzione(self):
        args = cli.build_parser().parse_args(["list-rows", "x.json"])
        self.assertTrue(callable(args.func))
        self.assertEqual(args.cmd, "list-rows")
        self.assertEqual(args.file, "x.json")


class MainTest(CLITestCase):
    def test_version(self):
        code, out, _ = self.run_cli("--version")
        self.assertEqual(code, 0)
        self.assertIn(f"grafana-utils {__version__}", out)

    def test_help(self):
        code, out, _ = self.run_cli("--help")
        self.assertEqual(code, 0)
        self.assertIn("list-rows", out)

    def test_senza_comando_e_errore_d_uso(self):
        code, _, err = self.run_cli()
        self.assertEqual(code, 2)
        self.assertIn("usage", err)
        self.assertEqual(len(self.logs("usage")), 1)

    def test_comando_sconosciuto(self):
        code, _, _ = self.run_cli("boh")
        self.assertEqual(code, 2)
        self.assertEqual(len(self.logs("usage")), 1)

    def test_input_mancante(self):
        code, _, err = self.run_cli("list-rows", str(self.tmp / "nope.json"))
        self.assertEqual(code, 2)
        self.assertIn("Errore input:", err)
        self.assertEqual(len(self.logs("input")), 1)

    def test_json_malformato(self):
        bad = self.tmp / "bad.json"
        bad.write_text("{", encoding="utf-8")
        code, _, _ = self.run_cli("validate", str(bad))
        self.assertEqual(code, 2)
        self.assertEqual(len(self.logs("input")), 1)

    def test_errore_di_output(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("copy-panel", src, "--panel-id", "2", "-o", str(self.tmp))
        self.assertEqual(code, 3)
        self.assertIn("Errore output:", err)
        self.assertEqual(len(self.logs("output")), 1)

    def test_errore_di_comando(self):
        src = self.write_json("in.json", sample_dashboard())
        code, _, err = self.run_cli("replace", src, "--replace", "senza-uguale")
        self.assertEqual(code, 1)
        self.assertIn("Errore:", err)
        self.assertEqual(len(self.logs("command")), 1)

    def test_read_only_con_none_esce_zero(self):
        src = self.write_json("in.json", sample_dashboard())
        code, out, _ = self.run_cli("list-rows", src)
        self.assertEqual(code, 0)
        self.assertIn("Row A", out)

    def test_log_contiene_gli_argomenti(self):
        self.run_cli("boh")
        log = self.logs("usage")[0].read_text(encoding="utf-8")
        self.assertIn("argv: boh", log)
        self.assertIn("type: USAGE_ERROR", log)

    def test_input_non_viene_mai_modificato(self):
        db = sample_dashboard()
        src = self.write_json("in.json", db)
        self.run_cli("replace", src, "--replace", "up=down")
        self.assertEqual(self.read_json(src), db)

    def test_pannello_non_riga_resta_intatto_dopo_errore(self):
        src = self.write_json("in.json", {"panels": [panel(1, "a")]})
        code, _, _ = self.run_cli("move-panel", src, "--panel-id", "1", "--target-row", "99")
        self.assertEqual(code, 1)
        self.assertTrue(self.read_json(src)["panels"])


if __name__ == "__main__":
    unittest.main()
