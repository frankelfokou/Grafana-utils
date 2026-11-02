"""Test di `grafana_tool.command_base.WriteCommand` (Template Method)."""
from __future__ import annotations

import argparse
import unittest
from pathlib import Path

from grafana_tool.command_base import WriteCommand
from grafana_tool.cli_common import add_write_options
from tests.support import CLITestCase, panel


class DummyCommand(WriteCommand):
    NAME = "dummy"
    HELP = "comando di test"

    def configure(self, parser):
        parser.add_argument("file")
        add_write_options(parser)

    def modify(self, db, args):
        db["modified"] = True
        return db


class WriteCommandTest(CLITestCase):
    def _args(self, **kw):
        base = {"file": None, "output": None, "dry_run": False,
                "lint_severity": "error", "cmd": "dummy"}
        base.update(kw)
        return argparse.Namespace(**base)

    def test_modify_base_restituisce_la_dashboard(self):
        db = {"a": 1}
        self.assertIs(WriteCommand().modify(db, None), db)

    def test_run_carica_modifica_e_salva(self):
        src = self.write_json("in.json", {"panels": [panel(1, "a")]})
        out = self.tmp / "out.json"
        code = DummyCommand().run(self._args(file=src, output=str(out)))
        self.assertEqual(code, 0)
        self.assertTrue(self.read_json(out)["modified"])

    def test_input_non_viene_modificato(self):
        original = {"panels": [panel(1, "a")]}
        src = self.write_json("in.json", original)
        out = self.tmp / "out.json"
        DummyCommand().run(self._args(file=src, output=str(out)))
        self.assertEqual(self.read_json(src), original)

    def test_modify_riceve_una_copia_profonda(self):
        seen = []

        class Spy(WriteCommand):
            def modify(self, db, args):
                seen.append(db)
                db["panels"][0]["title"] = "mutato"
                return db

        src = self.write_json("in.json", {"panels": [panel(1, "a")]})
        Spy().run(self._args(file=src, output=str(self.tmp / "out.json")))
        self.assertEqual(seen[0]["panels"][0]["title"], "mutato")
        self.assertEqual(self.read_json(src)["panels"][0]["title"], "a")

    def test_default_output_accanto_all_input(self):
        src = self.write_json("in.json", {"panels": []})
        DummyCommand().run(self._args(file=src))
        self.assertTrue((self.tmp / "in_out.json").exists())
        self.assertTrue(Path(src).exists())


if __name__ == "__main__":
    unittest.main()
