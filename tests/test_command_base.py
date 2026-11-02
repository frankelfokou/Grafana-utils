"""Test di `grafana_tool.command_base`: Template Method delle famiglie di comandi."""
from __future__ import annotations

import argparse
import io
import unittest
from contextlib import redirect_stdout
from pathlib import Path

from grafana_tool.command_base import ReadCommand, WriteCommand
from tests.support import CLITestCase, panel


class DummyCommand(WriteCommand):
    NAME = "dummy"
    HELP = "comando di test"

    def modify(self, db, args):
        db["modified"] = True
        return db


class ReadDummyCommand(ReadCommand):
    NAME = "read-dummy"
    HELP = "comando di lettura di test"

    def add_arguments(self, parser):
        parser.add_argument("--note", default="")

    def perform(self, db, args):
        print(f"{len(db.get('panels') or [])} pannelli; note={args.note}")
        return 0


class ConfigureTest(unittest.TestCase):
    """La classe base aggiunge da sola le opzioni comuni."""

    def _parser(self, command) -> argparse.ArgumentParser:
        parser = argparse.ArgumentParser(prog=command.NAME)
        command.configure(parser)
        return parser

    def test_write_command_aggiunge_file_e_opzioni_comuni(self):
        args = self._parser(DummyCommand()).parse_args(["x.json"])
        self.assertEqual(args.file, "x.json")
        self.assertIsNone(args.output)
        self.assertFalse(args.dry_run)
        self.assertEqual(args.severity, "error")

    def test_read_command_aggiunge_solo_il_file(self):
        args = self._parser(ReadDummyCommand()).parse_args(["x.json", "--note", "n"])
        self.assertEqual(args.file, "x.json")
        self.assertEqual(args.note, "n")
        self.assertFalse(hasattr(args, "output"))
        self.assertFalse(hasattr(args, "severity"))


class ReadCommandTest(CLITestCase):
    def test_run_carica_e_chiama_perform(self):
        src = self.write_json("in.json", {"panels": [panel(1, "a"), panel(2, "b")]})
        args = argparse.Namespace(file=src, note="x", cmd="read-dummy")
        out = io.StringIO()
        with redirect_stdout(out):
            code = ReadDummyCommand().run(args)
        self.assertEqual(code, 0)
        self.assertIn("2 pannelli; note=x", out.getvalue())

    def test_perform_base_non_implementato(self):
        with self.assertRaises(NotImplementedError):
            ReadCommand().perform({}, None)


class WriteCommandTest(CLITestCase):
    def _args(self, **kw):
        base = {"file": None, "output": None, "dry_run": False,
                "severity": "error", "cmd": "dummy"}
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

    def test_report_renamed_stampa_solo_se_ce_ne_sono(self):
        out = io.StringIO()
        with redirect_stdout(out):
            DummyCommand().report_renamed(0)
            DummyCommand().report_renamed(3)
        self.assertEqual(out.getvalue().strip(), "Titoli pannelli disambiguati: 3.")


if __name__ == "__main__":
    unittest.main()
