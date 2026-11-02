"""Responsabilità unica: costruire il parser e fare dispatch ai comandi."""
from __future__ import annotations

import argparse
import sys

from grafana_tool import __version__, errors
from grafana_tool.commands import ALL_COMMANDS
from grafana_tool.io import InputError, OutputError


class CommandParser(argparse.ArgumentParser):
    """Parser che registra gli errori d'uso in `out/` prima di uscire con 2."""

    # argv effettivamente in esame, così il log non dipende da sys.argv
    # quando la CLI è invocata con `main([...])`.
    argv: list[str] = []

    def error(self, message: str) -> None:
        errors.log_error(
            "usage",
            message,
            command=self.prog,
            argv=self.argv or sys.argv[1:],
            exit_code=2,
        )
        super().error(message)


def build_parser(argv: list[str] | None = None) -> argparse.ArgumentParser:
    p = CommandParser(
        prog="grafana-utils",
        description="CLI modulare per manipolare dashboard Grafana (JSON).",
        epilog=(
            "Contratto I/O: il file di input non viene mai modificato. Senza -o "
            "il risultato va in <input>_out.json, con -o nel path indicato. Se "
            "la validazione finale fallisce, al nome viene appeso "
            "_ERROR_<TIPO> e il report va in out/. Exit code: 1 = comando, "
            "validazione o lint falliti; 2 = errore di input; 3 = errore di output."
        ),
    )
    p.add_argument("--version", action="version", version=f"%(prog)s {__version__}")
    p.argv = list(argv or [])
    sub = p.add_subparsers(dest="cmd", required=True)

    for cmd in ALL_COMMANDS:
        sp = sub.add_parser(cmd.NAME, help=cmd.HELP)
        cmd.configure(sp)
        sp.set_defaults(func=cmd.run)

    return p


def _fail(kind: str, exc: Exception, code: int, args, argv: list[str]) -> int:
    """Registra l'errore e restituisce l'exit code."""
    errors.log_error(
        kind,
        str(exc),
        command=getattr(args, "cmd", None),
        argv=argv,
        exit_code=code,
    )
    return code


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    parser = build_parser(argv)
    args = parser.parse_args(argv)
    try:
        rc = args.func(args)
    except InputError as e:
        print(f"Errore input: {e}", file=sys.stderr)
        return _fail("input", e, 2, args, argv)
    except OutputError as e:
        print(f"Errore output: {e}", file=sys.stderr)
        return _fail("output", e, 3, args, argv)
    except FileNotFoundError as e:
        # fallback per path non gestiti esplicitamente da load/save
        print(f"File non trovato: {e.filename}", file=sys.stderr)
        return _fail("input", e, 2, args, argv)
    except ValueError as e:
        print(f"Errore: {e}", file=sys.stderr)
        return _fail("command", e, 1, args, argv)
    return int(rc) if rc else 0


if __name__ == "__main__":
    sys.exit(main())
