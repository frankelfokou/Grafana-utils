#!/usr/bin/env python3
"""Matrice di test esaustiva della CLI su dashboard-classic.json e dashboard-v2.json.

Esegue ogni comando con le sue combinazioni di parametri, poi verifica che ogni
file prodotto rispetti i criteri del contratto:

  1. il JSON è un oggetto, nel formato atteso (`--to-format` o quello d'ingresso);
  2. nessuna chiave interna (`_tabs`, `_tab`, `_element`, `_extras`, `_relative_grid`);
  3. il file è rileggibile dal tool e gli id sono interi e unici;
  4. in v2 ogni elemento è collocato una sola volta e il layout non cita fantasmi;
  5. le variabili conservano nome, valore, query e datasource; `hide` è
     normalizzato salvo `--keep-variable-visibility`;
  6. i valori fissi con il nome di una variabile sono sostituiti salvo
     `--keep-literal-values`;
  7. dentro una riga i pannelli non si sovrappongono;
  8. la validazione finale passa (nessun errore strutturale o di lint);
  9. il file di input non viene mai modificato.

I comandi che devono fallire vengono verificati per exit code, messaggio e
assenza di file di output.

Uso:  python3 tests/matrix/run_matrix.py   (oppure `python3 -m unittest discover -s tests`)

Gli artefatti (file prodotti, log, report) finiscono in `test-output/matrix/`,
che è ignorata da git: la cartella del test contiene solo il runner.
"""
from __future__ import annotations

import contextlib
import copy
import io as stdio
import json
import os
import re
import shutil
import sys
from dataclasses import dataclass, field
from typing import Any, Callable

# tests/matrix/run_matrix.py → tests/matrix → tests → radice del progetto
ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
WORKSPACE = os.path.dirname(ROOT)
ARTIFACTS = os.path.join(ROOT, "test-output", "matrix")
sys.path.insert(0, ROOT)

from grafana_tool import cli, formats, model, schema, tabs, validation  # noqa: E402
from grafana_tool.formats import dashboard as dashboard_adapter  # noqa: E402
from grafana_tool.formats import variables  # noqa: E402

WORK = os.path.join(ARTIFACTS, "work")
LOGS = os.path.join(WORK, "logs")
REPORT_MD = os.path.join(ARTIFACTS, "report.md")
REPORT_JSON = os.path.join(ARTIFACTS, "report.json")

SOURCES = {
    "classic": os.path.join(WORKSPACE, "dashboard-classic.json"),
    "v2": os.path.join(WORKSPACE, "dashboard-v2.json"),
}
SYNTH = os.path.join(WORK, "sources")


# ---------------------------------------------------------------- esecuzione


@dataclass
class Run:
    code: int
    out: str
    err: str
    argv: list[str]


def run(argv: list[str]) -> Run:
    """Esegue la CLI in-process catturando stdout, stderr ed exit code."""
    out, err = stdio.StringIO(), stdio.StringIO()
    code = 0
    try:
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            code = cli.main(argv) or 0
    except SystemExit as exc:  # argparse: --help, --version, errori d'uso
        code = int(exc.code or 0)
    return Run(code, out.getvalue(), err.getvalue(), argv)


# ------------------------------------------------------------------- fatti


@dataclass
class Facts:
    key: str
    path: str
    raw: dict[str, Any]
    db: dict[str, Any]
    fmt: str = schema.CLASSIC

    @property
    def rows(self) -> list[dict[str, Any]]:
        return list(model.iter_rows(self.db))

    @property
    def panels(self) -> list[dict[str, Any]]:
        return content(self.db)

    @property
    def tab_ids(self) -> list[int]:
        return [t["id"] for t in tabs.all_tabs(self.db)]

    @property
    def tab_list(self) -> list[dict[str, Any]]:
        return tabs.all_tabs(self.db)


def content(db: dict[str, Any]) -> list[dict[str, Any]]:
    return [p for _, _, p, _ in model.iter_panel_slots(db) if p.get("type") != "row"]


def load_facts(key: str, path: str) -> Facts:
    with open(path, encoding="utf-8") as f:
        raw = json.load(f)
    db = formats.load(copy.deepcopy(raw)).db
    return Facts(key, path, raw, db, schema.detect(raw))


# ---------------------------------------------------------------- controlli


def find_internal(obj: Any, path: str = "root") -> list[str]:
    found: list[str] = []
    if isinstance(obj, dict):
        for key, value in obj.items():
            if key in schema.INTERNAL_KEYS:
                found.append(f"{path}.{key}")
            found.extend(find_internal(value, f"{path}.{key}"))
    elif isinstance(obj, list):
        for i, value in enumerate(obj):
            found.extend(find_internal(value, f"{path}[{i}]"))
    return found


def element_refs(node: Any, acc: list[str] | None = None) -> list[str]:
    acc = [] if acc is None else acc
    if isinstance(node, dict):
        if node.get("kind") == "ElementReference" and isinstance(node.get("name"), str):
            acc.append(node["name"])
        for value in node.values():
            element_refs(value, acc)
    elif isinstance(node, list):
        for value in node:
            element_refs(value, acc)
    return acc


def rect(panel: dict[str, Any]) -> tuple[int, int, int, int] | None:
    grid = panel.get("gridPos")
    if not isinstance(grid, dict):
        return None
    values = [grid.get(k) for k in ("x", "y", "w", "h")]
    if not all(isinstance(v, int) and not isinstance(v, bool) for v in values):
        return None
    return tuple(values)  # type: ignore[return-value]


def overlap(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> bool:
    return a[0] < b[0] + b[2] and b[0] < a[0] + a[2] and a[1] < b[1] + b[3] and b[1] < a[1] + a[3]


def row_overlaps(db: dict[str, Any]) -> list[tuple[Any, Any, Any]]:
    """Sovrapposizioni tra i pannelli della stessa riga (lo spazio è per riga)."""
    found = []
    for row in model.iter_rows(db):
        kids = [c for c in model.row_children(db, row) if isinstance(c, dict)]
        for i in range(len(kids)):
            for j in range(i + 1, len(kids)):
                a, b = rect(kids[i]), rect(kids[j])
                if a and b and overlap(a, b):
                    found.append((row.get("id"), kids[i].get("id"), kids[j].get("id")))
    return found


def block_overlaps(db: dict[str, Any]) -> list[tuple[str, Any, str, Any]]:
    """Sovrapposizioni tra oggetti di primo livello di una dashboard classica."""
    entries: list[tuple[str, Any, tuple[int, int, int, int]]] = []
    expanded: dict | None = None
    for item in db.get("panels") or []:
        if not isinstance(item, dict):
            continue
        if item.get("type") == "row":
            expanded = item if item.get("collapsed") is False else None
            r = rect(item)
            if r:
                entries.append(("row", item.get("id"), r))
        elif expanded is not None:
            r = rect(item)
            if r:
                entries.append(("panel", item.get("id"), r))
    found = []
    for i in range(len(entries)):
        for j in range(i + 1, len(entries)):
            a, b = entries[i], entries[j]
            if overlap(a[2], b[2]):
                found.append((a[0], a[1], b[0], b[1]))
    return found


def var_snapshot(db: dict[str, Any]) -> dict[str, Any]:
    """Variabili canoniche senza `hide`: è ciò che non deve mai cambiare."""
    snap = {}
    for var in variables._variable_list(db):
        if isinstance(var, dict):
            snap[var.get("name")] = {
                k: copy.deepcopy(v) for k, v in var.items() if k != "hide"
            }
    return snap


def hide_map(db: dict[str, Any]) -> dict[str, Any]:
    return {
        var.get("name"): var.get("hide")
        for var in variables._variable_list(db)
        if isinstance(var, dict)
    }


def substitutable_names(db: dict[str, Any]) -> set[str]:
    return {
        var["name"]
        for var in variables._variable_list(db)
        if isinstance(var, dict)
        and var.get("type") in variables.SUBSTITUTABLE_TYPES
        and isinstance(var.get("name"), str)
    }


def literal_hits(db: dict[str, Any]) -> list[tuple[Any, str]]:
    names = substitutable_names(db)
    hits = []
    for _, _, panel, _ in model.iter_panel_slots(db):
        for target in panel.get("targets") or []:
            expr = target.get("expr") if isinstance(target, dict) else None
            if not isinstance(expr, str):
                continue
            for match in variables.LABEL_MATCHER.finditer(expr):
                if match.group("label") in names:
                    hits.append((panel.get("id"), match.group(0)))
    return hits


def layout_element_names(raw: dict[str, Any]) -> list[str]:
    """Nomi usati in `elements`, ricavati dal layout (ordine di collocazione)."""
    return element_refs(raw.get("layout"), [])


@dataclass
class Ctx:
    case: "Case"
    facts: Facts
    out_path: str | None
    out_raw: dict[str, Any] | None
    out_db: dict[str, Any] | None
    run: Run
    expected_format: str = ""
    check_blocks: bool = False
    check_rows: bool = True

    @property
    def keep_vis(self) -> bool:
        return "--keep-variable-visibility" in self.run.argv

    @property
    def keep_lit(self) -> bool:
        return "--keep-literal-values" in self.run.argv

    @property
    def src_literals(self) -> int:
        return len(literal_hits(self.facts.db))


def generic_checks(ctx: Ctx) -> list[str]:
    problems: list[str] = []
    raw, db = ctx.out_raw or {}, ctx.out_db or {}

    detected = schema.detect(raw)
    if detected != ctx.expected_format:
        problems.append(f"formato {detected!r}, atteso {ctx.expected_format!r}")

    for path in find_internal(raw):
        problems.append(f"chiave interna esportata: {path}")

    if ctx.expected_format == schema.V2:
        for key in dashboard_adapter.V2_ABSENT_KEYS:
            if raw.get(key) not in (None,):
                problems.append(f"v2 con '{key}' = {raw.get(key)!r}")
        elements = raw.get("elements")
        if not isinstance(elements, dict) or not elements:
            problems.append("'elements' assente o vuoto")
            elements = {}
        refs = layout_element_names(raw)
        duplicates = sorted({n for n in refs if refs.count(n) > 1})
        if duplicates:
            problems.append(f"elementi collocati più volte: {duplicates[:5]}")
        missing = sorted(set(refs) - set(elements))
        if missing:
            problems.append(f"layout cita elementi assenti: {missing[:5]}")
        unplaced = sorted(set(elements) - set(refs))
        if unplaced:
            problems.append(f"elementi non collocati: {unplaced[:5]}")
    else:
        if not isinstance(raw.get("panels"), list):
            problems.append("'panels' assente")
        if "elements" in raw or "layout" in raw:
            problems.append("residui v2 in un file classico")

    ids = [p.get("id") for p in model.iter_all_panels(db)]
    bad = [i for i in ids if not (isinstance(i, int) and not isinstance(i, bool))]
    if bad:
        problems.append(f"id non interi: {bad[:5]}")
    duplicates = sorted({i for i in ids if ids.count(i) > 1})
    if duplicates:
        problems.append(f"id duplicati: {duplicates[:5]}")

    known = {t.get("id") for t in tabs.all_tabs(db)}
    if not known:
        problems.append("nessun tab canonico")
    for row in model.iter_rows(db):
        if schema.tab_of(row) not in known:
            problems.append(f"riga {row.get('id')} con tab {schema.tab_of(row)} inesistente")

    result = validation.check(db, "error")
    if result.errors:
        problems.append(f"validazione: {result.errors}")
    lint_errors = [i for i in result.issues if i.severity == "error"]
    if lint_errors:
        problems.append(f"lint error: {[i.code for i in lint_errors][:5]}")

    if ctx.expected_format == schema.CLASSIC:
        if ctx.check_rows:
            overlaps = row_overlaps(db)
            if overlaps:
                problems.append(
                    f"sovrapposizioni dentro la riga: {overlaps[:3]} (tot {len(overlaps)})"
                )
        if ctx.check_blocks:
            blocks = block_overlaps(db)
            if blocks:
                problems.append(f"sovrapposizioni di primo livello: {blocks[:3]} (tot {len(blocks)})")
    return problems


def variable_checks(ctx: Ctx) -> list[str]:
    problems: list[str] = []
    before, after = var_snapshot(ctx.facts.db), var_snapshot(ctx.out_db or {})
    if before != after:
        for name in sorted(set(before) | set(after)):
            if before.get(name) != after.get(name):
                problems.append(f"variabile {name!r} modificata")

    hides = hide_map(ctx.out_db or {})
    if ctx.keep_vis:
        if hides != hide_map(ctx.facts.db):
            problems.append("--keep-variable-visibility ma hide è cambiato")
    else:
        hidden = {k: v for k, v in hides.items() if v not in variables.VISIBLE_HIDE}
        if hidden:
            problems.append(f"variabili non visibili in alto: {hidden}")

    hits = literal_hits(ctx.out_db or {})
    if ctx.keep_lit:
        if len(hits) != ctx.src_literals:
            problems.append(
                f"--keep-literal-values ma i matcher fissi sono {len(hits)} invece di {ctx.src_literals}"
            )
    elif hits:
        problems.append(f"{len(hits)} matcher con valore fisso residui: {hits[:3]}")
    return problems


# ------------------------------------------------------------ verifiche puntuali


def sem(expected: Callable[[Ctx], list[str]]) -> Callable[[Ctx], list[str]]:
    return expected


def run_count(db: dict[str, Any]) -> tuple[int, int]:
    return len(list(model.iter_rows(db))), len(content(db))


def expect_counts(delta_rows: int = 0, delta_panels: int = 0) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        before = run_count(ctx.facts.db)
        after = run_count(ctx.out_db or {})
        problems = []
        if after[0] != before[0] + delta_rows:
            problems.append(f"righe {after[0]}, attese {before[0] + delta_rows}")
        if after[1] != before[1] + delta_panels:
            problems.append(f"pannelli {after[1]}, attesi {before[1] + delta_panels}")
        return problems

    return check


def expect_panel_gone(panel_id: int) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        if any(p.get("id") == panel_id for p in model.iter_all_panels(ctx.out_db or {})):
            return [f"pannello {panel_id} ancora presente"]
        return []

    return check


def expect_row_gone(row_id: int, children_gone: bool) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        problems = []
        db = ctx.out_db or {}
        source = next(r for r in ctx.facts.rows if r.get("id") == row_id)
        title = source.get("title") or ""
        if any((r.get("title") or "") == title for r in model.iter_rows(db)):
            problems.append(f"riga {title!r} ancora presente")
        if children_gone:
            ids = [c.get("id") for c in model.row_children(ctx.facts.db, source)]
            alive = {p.get("id") for p in model.iter_all_panels(db)}
            left = [i for i in ids if i in alive]
            if left:
                problems.append(f"figli della riga {title!r} ancora presenti: {left[:5]}")
        return problems

    return check


def expect_row_title(row_id: int, title: str) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        titles = [(r.get("title") or "") for r in model.iter_rows(ctx.out_db or {})]
        if title not in titles:
            return [f"nessuna riga con titolo {title!r}"]
        return []

    return check


def expect_tab_title(tab_id: int, title: str) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        for tab in tabs.all_tabs(ctx.out_db or {}):
            if tab.get("id") == tab_id:
                if (tab.get("title") or "") != title:
                    return [f"titolo tab {tab.get('title')!r}, atteso {title!r}"]
                return []
        return [f"tab {tab_id} non trovato"]

    return check


def expect_title(obj_id: int, title: str) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        for panel in model.iter_all_panels(ctx.out_db or {}):
            if panel.get("id") == obj_id:
                if panel.get("title") != title:
                    return [f"titolo {panel.get('title')!r}, atteso {title!r}"]
                return []
        return [f"oggetto {obj_id} non trovato"]

    return check


def expect_title_prefix(obj_id: int, prefix: str) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        for panel in model.iter_all_panels(ctx.out_db or {}):
            if panel.get("id") == obj_id:
                title = panel.get("title") or ""
                if not title.startswith(prefix):
                    return [f"titolo {title!r} senza prefisso {prefix!r}"]
                return []
        return [f"oggetto {obj_id} non trovato"]

    return check


def expect_datasource(uid: str, panel_id: int) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        problems = []
        for panel in content(ctx.out_db or {}):
            if panel.get("id") != panel_id:
                continue
            ds = panel.get("datasource")
            if isinstance(ds, dict) and ds.get("uid") != uid:
                problems.append(f"pannello {panel.get('id')} datasource {ds.get('uid')!r}")
            for target in panel.get("targets") or []:
                tds = target.get("datasource") if isinstance(target, dict) else None
                if isinstance(tds, dict) and tds.get("uid") != uid:
                    problems.append(f"target in {panel.get('id')} datasource {tds.get('uid')!r}")
                    break
            return problems
        return [f"pannello {panel_id} non trovato"]

    return check


def expect_expr_contains(text: str) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        exprs = [
            t.get("expr", "")
            for p in model.iter_all_panels(ctx.out_db or {})
            for t in p.get("targets") or []
            if isinstance(t, dict)
        ]
        if not any(text in e for e in exprs):
            return [f"nessuna expr contiene {text!r}"]
        return []

    return check


def expect_row_parent(panel_id: int, row_id: int) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        source = next(r for r in ctx.facts.rows if r.get("id") == row_id)
        wanted = source.get("title") or ""
        for _, _, panel, row in model.iter_panel_slots(ctx.out_db or {}):
            if panel.get("id") == panel_id:
                got = (row.get("title") or "") if row else None
                if got != wanted:
                    return [f"pannello {panel_id} nella riga {got!r}, attesa {wanted!r}"]
                return []
        return [f"pannello {panel_id} non trovato"]

    return check


def expect_row_tab(row_id: int, tab_id: int) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        source = next(r for r in ctx.facts.rows if r.get("id") == row_id)
        wanted = source.get("title") or ""
        for row in model.iter_rows(ctx.out_db or {}):
            if (row.get("title") or "") == wanted:
                if schema.tab_of(row) != tab_id:
                    return [f"riga {wanted!r} nel tab {schema.tab_of(row)}, atteso {tab_id}"]
                return []
        return [f"riga {wanted!r} non trovata"]

    return check


def expect_tab_titles(titles: list[str]) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        got = [(t.get("title") or "") for t in tabs.all_tabs(ctx.out_db or {})]
        return [] if got == titles else [f"ordine tab {got}, atteso {titles}"]

    return check


def expect_row_titles_order(titles: list[str]) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        got = [(r.get("title") or "") for r in model.iter_rows(ctx.out_db or {})]
        return [] if got == titles else [f"ordine righe {got}, atteso {titles}"]

    return check


def expect_row_panel_order(row_id: int, first: int, second: int) -> Callable[[Ctx], list[str]]:
    """`first` deve precedere `second` dentro la riga indicata."""

    def check(ctx: Ctx) -> list[str]:
        source = next(r for r in ctx.facts.rows if r.get("id") == row_id)
        title = source.get("title") or ""
        db = ctx.out_db or {}
        for row in model.iter_rows(db):
            if (row.get("title") or "") != title:
                continue
            ids = [c.get("id") for c in model.row_children(db, row)]
            if first in ids and second in ids:
                return [] if ids.index(first) < ids.index(second) else [f"ordine pannelli {ids}"]
            return [f"pannelli {first}, {second} non entrambi nella riga {title!r}"]
        return [f"riga {title!r} non trovata"]

    return check


def expect_file_absent(path: str) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        return [f"file scritto nonostante --dry-run: {path}"] if os.path.exists(path) else []

    return check


def expect_file_present(path: str) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        return [] if os.path.exists(path) else [f"file atteso assente: {path}"]

    return check


def expect_root(uid: str | None = None, title: str | None = None) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        raw = ctx.out_raw or {}
        problems = []
        if uid is not None and raw.get("uid") != uid:
            problems.append(f"uid {raw.get('uid')!r}, atteso {uid!r}")
        if title is not None and raw.get("title") != title:
            problems.append(f"titolo {raw.get('title')!r}, atteso {title!r}")
        return problems

    return check


def expect_first_id(first: int) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        ids = sorted(p.get("id") for p in model.iter_all_panels(ctx.out_db or {}))
        return [] if ids and ids[0] == first else [f"primo id {ids[0] if ids else None}, atteso {first}"]

    return check


def expect_ids_include(identifier: int) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        ids = [p.get("id") for p in model.iter_all_panels(ctx.out_db or {})]
        return [] if identifier in ids else [f"id {identifier} assente da {ids[-5:]}"]

    return check


def expect_no_datasource(panel_id: int) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        for panel in model.iter_all_panels(ctx.out_db or {}):
            if panel.get("id") == panel_id:
                return [] if not panel.get("datasource") else ["datasource creato senza --datasource-create"]
        return [f"pannello {panel_id} non trovato"]

    return check


def expect_tab_order(order: list[Any]) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        got = [t.get("id") for t in tabs.all_tabs(ctx.out_db or {})]
        return [] if got == order else [f"ordine tab {got}, atteso {order}"]

    return check


def expect_single_tab() -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        got = [t.get("id") for t in tabs.all_tabs(ctx.out_db or {})]
        return [] if len(got) == 1 else [f"tab {got}, atteso uno solo"]

    return check


def expect_ids_contiguous() -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        ids = sorted(p.get("id") for p in model.iter_all_panels(ctx.out_db or {}))
        expected = list(range(1, len(ids) + 1))
        return [] if ids == expected else [f"id {ids[:6]}..., attesi 1..{len(ids)}"]

    return check


def expect_identity(title_differs: bool = True) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        raw = ctx.out_raw or {}
        if ctx.expected_format == schema.V2:
            return [f"v2 con uid {raw.get('uid')!r}"] if raw.get("uid") else []
        problems = []
        if raw.get("id") is not None:
            problems.append(f"id = {raw.get('id')!r}")
        if raw.get("version") != 1:
            problems.append(f"version = {raw.get('version')!r}")
        if not raw.get("uid"):
            problems.append("uid assente")
        elif raw.get("uid") == ctx.facts.raw.get("uid"):
            problems.append("uid uguale alla sorgente")
        if title_differs and raw.get("title") == ctx.facts.raw.get("title"):
            problems.append("titolo uguale alla sorgente")
        return problems

    return check


def expect_no_uid() -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        raw = ctx.out_raw or {}
        return [f"v2 con uid {raw.get('uid')!r}"] if raw.get("uid") else []

    return check


def expect_no_binding(kind: str) -> Callable[[Ctx], list[str]]:
    """`kind` = library | alert | links."""

    def check(ctx: Ctx) -> list[str]:
        db = ctx.out_db or {}
        if kind == "library":
            found = [p.get("id") for p in model.iter_all_panels(db) if p.get("libraryPanel")]
        elif kind == "alert":
            found = [
                p.get("id")
                for p in model.iter_all_panels(db)
                if p.get("alert") or p.get("alertId")
            ]
        else:
            found = ["dashboard"] if (db.get("links") or []) else []
        return [f"{kind} ancora presente in {found[:5]}"] if found else []

    return check


def expect_has_binding(kind: str) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        db = ctx.out_db or {}
        if kind == "library":
            ok = any(p.get("libraryPanel") for p in model.iter_all_panels(db))
        elif kind == "alert":
            ok = any(p.get("alert") or p.get("alertId") for p in model.iter_all_panels(db))
        else:
            ok = bool(db.get("links"))
        return [] if ok else [f"{kind} assente"]

    return check


def expect_panel_count(n: int) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        got = len(content(ctx.out_db or {}))
        return [] if got == n else [f"{got} pannelli, attesi {n}"]

    return check


def expect_target_count() -> Callable[[Ctx], list[str]]:
    """Le query non spariscono e non si duplicano in una conversione."""

    def check(ctx: Ctx) -> list[str]:
        def count(db: dict[str, Any]) -> int:
            return sum(
                len(p.get("targets") or [])
                for p in content(db)
                if isinstance(p.get("targets"), list)
            )

        before, after = count(ctx.facts.db), count(ctx.out_db or {})
        return [] if before == after else [f"query {after}, attese {before}"]

    return check


def expect_json_stdout(expected_len: int | None = None) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        try:
            payload = json.loads(ctx.run.out)
        except json.JSONDecodeError as exc:
            return [f"stdout non è JSON: {exc}"]
        if expected_len is not None and len(payload) != expected_len:
            return [f"{len(payload)} elementi, attesi {expected_len}"]
        return []

    return check


def expect_contains(text: str) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        blob = ctx.run.out + ctx.run.err
        return [] if text in blob else [f"messaggio senza {text!r}"]

    return check


def expect_not_contains(text: str) -> Callable[[Ctx], list[str]]:
    def check(ctx: Ctx) -> list[str]:
        blob = ctx.run.out + ctx.run.err
        return [f"output contiene {text!r}"] if text in blob else []

    return check


# ------------------------------------------------------------------ casi


@dataclass
class Case:
    name: str
    src: str
    args: Callable[[str | None], list[str]]
    expect: str = "ok"                      # ok | error
    output: bool = True                     # il caso produce un file di output
    semantic: list[Callable[[Ctx], list[str]]] = field(default_factory=list)
    check_blocks: bool = False
    check_rows: bool = True
    rc: int | None = None                   # exit code atteso per gli errori
    note: str = ""


CASES: list[Case] = []
OUTCOMES: list["Outcome"] = []
FACTS: dict[str, Facts] = {}


def add(name: str, src: str, args: Callable[[str | None], list[str]], **kwargs: Any) -> None:
    """Registra il caso e lo esegue subito.

    L'esecuzione immediata è deliberata: la lambda di `args` chiude sulle
    variabili del ciclo corrente (`key`, `f`, `target`, ...). Rimandarla alla
    fine farebbe leggere a tutti i casi l'ultimo valore del ciclo.
    """
    case = Case(name, src, args, **kwargs)
    index = len(CASES)
    CASES.append(case)
    try:
        OUTCOMES.append(execute(index, case, FACTS))
    except Exception as exc:  # noqa: BLE001
        import traceback

        OUTCOMES.append(
            Outcome(case.name, case.src, [], -1, "FAIL",
                    [f"eccezione nel test: {exc}", traceback.format_exc(limit=3)],
                    "", "")
        )


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:70]


def build_cases(facts: dict[str, Facts]) -> None:
    # ---------------------------------------------------------------- lettura
    for key, f in facts.items():
        if key not in ("classic", "v2"):
            continue
        first_panel = f.panels[0]["id"]
        first_row = f.rows[0]["id"]
        first_tab = f.tab_ids[0]
        last_tab = f.tab_ids[-1]
        for kind in ("row", "panel", "tab"):
            add(f"list {kind}", key, lambda out, k=kind: ["list", k, SOURCES[key]], output=False)
            add(
                f"list {kind} --format json",
                key,
                lambda out, k=kind: ["list", k, SOURCES[key], "--format", "json"],
                output=False,
                semantic=[expect_json_stdout()],
            )
        add(
            "list panel --id",
            key,
            lambda out: ["list", "panel", SOURCES[key], "--id", str(first_panel)],
            output=False,
        )
        add(
            "list panel --id json",
            key,
            lambda out: [
                "list", "panel", SOURCES[key], "--id", str(first_panel), "--format", "json"
            ],
            output=False,
            semantic=[expect_json_stdout(1)],
        )
        add(
            "list panel --match-type timeseries",
            key,
            lambda out: ["list", "panel", SOURCES[key], "--match-type", "timeseries"],
            output=False,
        )
        add(
            "list panel --in-row",
            key,
            lambda out: ["list", "panel", SOURCES[key], "--in-row", str(first_row)],
            output=False,
        )
        add(
            "list row --in-tab last",
            key,
            lambda out: ["list", "row", SOURCES[key], "--in-tab", str(last_tab)],
            output=False,
        )
        add(
            "list panel --in-tab last json",
            key,
            lambda out: [
                "list", "panel", SOURCES[key], "--in-tab", str(last_tab), "--format", "json"
            ],
            output=False,
            semantic=[expect_json_stdout()],
        )
        add(
            "list row --match-title .*",
            key,
            lambda out: ["list", "row", SOURCES[key], "--match-title", ".*"],
            output=False,
        )
        add(
            f"validate {key}",
            key,
            lambda out: ["validate", SOURCES[key]],
            output=False,
            semantic=[expect_contains("Validazione: nessun errore strutturale")],
        )
        add(
            f"validate {key} --severity warning",
            key,
            lambda out: ["validate", SOURCES[key], "--severity", "warning"],
            expect="error",
            rc=1,
            output=False,
        )
        add(
            f"lint {key}",
            key,
            lambda out: ["lint", SOURCES[key]],
            output=False,
        )
        add(
            f"lint {key} --format json",
            key,
            lambda out: ["lint", SOURCES[key], "--format", "json"],
            output=False,
            semantic=[expect_json_stdout()],
        )

    # ------------------------------------------- conversione: matrice completa
    for key, f in facts.items():
        if key not in ("classic", "v2"):
            continue
        panel = next(p for p in f.panels if p.get("title"))
        pid, ptitle = panel["id"], panel.get("title") or ""
        for target in (None, "classic", "v2"):
            for keep_vis in (False, True):
                for keep_lit in (False, True):
                    for drop in (False, True):
                        flags = []
                        if target:
                            flags += ["--to-format", target]
                        if keep_vis:
                            flags.append("--keep-variable-visibility")
                        if keep_lit:
                            flags.append("--keep-literal-values")
                        if drop:
                            flags.append("--drop-alerts")
                        name = (
                            f"update panel {key}->{target or 'default'}"
                            f"{' vis' if keep_vis else ''}"
                            f"{' lit' if keep_lit else ''}"
                            f"{' drop' if drop else ''}"
                        )
                        add(
                            name,
                            key,
                            lambda out, pid=pid, ptitle=ptitle, flags=flags: [
                                "update", "panel", SOURCES[key],
                                "--id", str(pid), "--title", ptitle,
                                "-o", out, *flags,
                            ],
                            semantic=[
                                expect_counts(),
                                expect_target_count(),
                                expect_title(pid, ptitle),
                                expect_single_tab() if target == "classic" or key == "classic" else (lambda ctx: []),
                            ],
                            check_blocks=target == "classic" or (target is None and key == "classic"),
                        )

    # ------------------------------------------------------------ creazione
    template_path = os.path.join(ROOT, "templates", "system-view.row.tpl.json")
    with open(template_path, encoding="utf-8") as fh:
        template = formats.load(copy.deepcopy(json.load(fh))).db
    template_panels = len(content(template))

    for key, f in facts.items():
        if key not in ("classic", "v2"):
            continue
        row = f.rows[0]
        row_id = row["id"]
        panel = f.panels[0]
        pid = panel["id"]
        last_tab = f.tab_ids[-1]
        add(
            "create tab",
            key,
            lambda out: ["create", "tab", SOURCES[key], "--title", "Tab nuovo", "-o", out],
            semantic=[expect_counts()],
        )
        add(
            "create tab --position top --dedupe-titles",
            key,
            lambda out: [
                "create", "tab", SOURCES[key], "--title", "Tab nuovo",
                "--position", "top", "--dedupe-titles", "--to-format", "v2", "-o", out,
            ],
            semantic=[expect_tab_titles(["Tab nuovo", *[t.get("title") or "" for t in f.tab_list]])],
        )
        add(
            "create tab su uscita classica (appiattisce)",
            key,
            lambda out: [
                "create", "tab", SOURCES[key], "--title", "Tab nuovo",
                "--position", "top", "--to-format", "classic", "-o", out,
            ],
            semantic=[expect_single_tab(), expect_counts()],
        )
        add(
            "create tab in v2",
            key,
            lambda out: ["create", "tab", SOURCES[key], "--title", "Nuovo", "--to-format", "v2", "-o", out],
            semantic=[expect_counts()],
        )
        add(
            "create row default template",
            key,
            lambda out: ["create", "row", SOURCES[key], "--title", "Riga nuova", "-o", out],
            semantic=[expect_counts(delta_rows=1, delta_panels=template_panels)],
            check_rows=False,
        )
        add(
            "create row --from-id",
            key,
            lambda out: [
                "create", "row", SOURCES[key], "--from-id", str(row_id),
                "--title", "Copia riga", "--dedupe-titles", "-o", out,
            ],
            semantic=[expect_counts(delta_rows=1, delta_panels=len(model.row_children(f.db, row)))],
        )
        add(
            "create row --to-tab last",
            key,
            lambda out: [
                "create", "row", SOURCES[key], "--title", "Riga tab",
                "--to-tab", str(last_tab), "-o", out,
            ],
            semantic=[expect_counts(delta_rows=1, delta_panels=template_panels)],
            check_rows=False,
        )
        add(
            "create row --expanded",
            key,
            lambda out: [
                "create", "row", SOURCES[key], "--title", "Riga espansa",
                "--expanded", "-o", out,
            ],
            semantic=[expect_counts(delta_rows=1, delta_panels=template_panels)],
            check_rows=False,
        )
        add(
            "create panel --from-id",
            key,
            lambda out: [
                "create", "panel", SOURCES[key], "--from-id", str(pid),
                "--title", "Pannello copia", "-o", out,
            ],
            semantic=[expect_counts(delta_panels=1)],
            check_rows=False,
        )
        add(
            "create panel --from-id --to-row",
            key,
            lambda out: [
                "create", "panel", SOURCES[key], "--from-id", str(pid),
                "--title", "Pannello in riga", "--to-row", str(row_id), "-o", out,
            ],
            semantic=[expect_counts(delta_panels=1)],
            check_rows=False,
        )
        add(
            "create panel --from-id v2",
            key,
            lambda out: [
                "create", "panel", SOURCES[key], "--from-id", str(pid),
                "--title", "Pannello v2", "--to-format", "v2", "-o", out,
            ],
            semantic=[expect_counts(delta_panels=1)],
        )

    # ------------------------------------------------------------- modifica
    for key, f in facts.items():
        if key not in ("classic", "v2"):
            continue
        row_id = f.rows[0]["id"]
        panel = f.panels[0]
        pid = panel["id"]
        data_panel = next(p for p in f.panels if p.get("targets"))
        add(
            "update row --title",
            key,
            lambda out: [
                "update", "row", SOURCES[key], "--id", str(row_id),
                "--title", "Riga rinominata", "-o", out,
            ],
            semantic=[expect_row_title(row_id, "Riga rinominata"), expect_counts()],
        )
        add(
            "update row --expanded",
            key,
            lambda out: [
                "update", "row", SOURCES[key], "--id", str(row_id),
                "--expanded", "-o", out,
            ],
            semantic=[expect_counts()],
            check_blocks=True,
        )
        add(
            "update row --collapsed",
            key,
            lambda out: [
                "update", "row", SOURCES[key], "--id", str(row_id),
                "--collapsed", "-o", out,
            ],
            semantic=[expect_counts()],
        )
        data_panel = next(p for p in f.panels if p.get("targets"))
        first_expr = next(
            (
                t.get("expr")
                for t in data_panel.get("targets") or []
                if isinstance(t, dict) and isinstance(t.get("expr"), str)
            ),
            "",
        )
        token = (re.findall(r"[A-Za-z_][A-Za-z0-9_]{5,}", first_expr) or ["sum"])[0]
        add(
            "update panel --datasource",
            key,
            lambda out: [
                "update", "panel", SOURCES[key], "--id", str(data_panel["id"]),
                "--datasource", "NUOVO-UID", "--datasource-type", "prometheus", "-o", out,
            ],
            semantic=[expect_datasource("NUOVO-UID", data_panel["id"]), expect_counts()],
        )
        add(
            "update panel --replace",
            key,
            lambda out, tok=token: [
                "update", "panel", SOURCES[key], "--id", str(data_panel["id"]),
                "--replace", f"{tok}={tok}_v2", "-o", out,
            ],
            semantic=[expect_expr_contains(f"{token}_v2"), expect_counts()],
        )
        add(
            "update tab --title",
            key,
            lambda out: [
                "update", "tab", SOURCES[key], "--id", str(f.tab_ids[0]),
                "--title", "Vista rinominata", "--to-format", "v2", "-o", out,
            ],
            semantic=[expect_tab_title(f.tab_ids[0], "Vista rinominata"), expect_counts()],
        )
        add(
            "update tab --replace v2",
            key,
            lambda out: [
                "update", "tab", SOURCES[key], "--id", str(f.tab_ids[0]),
                "--replace", "request_counter=request_counter_v2", "--to-format", "v2", "-o", out,
            ],
            semantic=[expect_counts()],
        )

    # ------------------------------------------------------------- rimozione
    for key, f in facts.items():
        if key not in ("classic", "v2"):
            continue
        row = f.rows[0]
        row_id = row["id"]
        row_children = len(model.row_children(f.db, row))
        panel = f.panels[-1]
        pid = panel["id"]
        add(
            "delete panel",
            key,
            lambda out: ["delete", "panel", SOURCES[key], "--id", str(pid), "-o", out],
            semantic=[expect_panel_gone(pid), expect_counts(delta_panels=-1)],
        )
        add(
            "delete row",
            key,
            lambda out: ["delete", "row", SOURCES[key], "--id", str(row_id), "-o", out],
            semantic=[
                expect_row_gone(row_id, True),
                expect_counts(delta_rows=-1, delta_panels=-row_children),
            ],
        )
        add(
            "delete row --keep-children",
            key,
            lambda out: [
                "delete", "row", SOURCES[key], "--id", str(row_id),
                "--keep-children", "-o", out,
            ],
            semantic=[
                expect_row_gone(row_id, False),
                # in v2 i pannelli orfani finiscono in una riga sintetica:
                # il numero di righe resta uguale, in classico cala di uno
                expect_counts(
                    delta_rows=-1 if f.fmt == schema.CLASSIC else 0
                ),
            ],
            check_rows=False,
        )
        add(
            "delete panel v2",
            key,
            lambda out: [
                "delete", "panel", SOURCES[key], "--id", str(pid),
                "--to-format", "v2", "-o", out,
            ],
            semantic=[expect_panel_gone(pid), expect_counts(delta_panels=-1)],
        )
    # tab: solo dove ce ne sono due
    v2 = facts["v2"]
    add(
        "delete tab 2",
        "v2",
        lambda out: ["delete", "tab", SOURCES["v2"], "--id", "2", "-o", out],
        semantic=[
            expect_tab_titles([facts["v2"].tab_list[0].get("title") or ""]),
            expect_counts(
                delta_rows=-2,
                delta_panels=-len(tabs.panels_of(facts["v2"].db, 2)),
            ),
        ],
    )
    add(
        "delete tab 2 --keep-children",
        "v2",
        lambda out: [
            "delete", "tab", SOURCES["v2"], "--id", "2", "--keep-children", "-o", out
        ],
        semantic=[
            expect_tab_titles([facts["v2"].tab_list[0].get("title") or ""]),
            expect_counts(),
        ],
    )

    # ----------------------------------------------------------- spostamento
    for key, f in facts.items():
        if key not in ("classic", "v2"):
            continue
        first_row, second_row = f.rows[0]["id"], f.rows[1]["id"]
        panel = next(
            p for _, _, p, r in model.iter_panel_slots(f.db)
            if r is not None and r.get("id") == first_row and p.get("type") != "row"
        )
        pid = panel["id"]
        add(
            "move panel --to-row",
            key,
            lambda out: [
                "move", "panel", SOURCES[key], "--id", str(pid),
                "--to-row", str(second_row), "-o", out,
            ],
            semantic=[expect_row_parent(pid, second_row), expect_counts()],
            check_rows=False,
        )
        add(
            "move row --position top",
            key,
            lambda out: [
                "move", "row", SOURCES[key], "--id", str(second_row),
                "--position", "top", "-o", out,
            ],
            semantic=[expect_counts()],
        )
        add(
            "move row --before",
            key,
            lambda out: [
                "move", "row", SOURCES[key], "--id", str(second_row),
                "--before", str(first_row), "-o", out,
            ],
            semantic=[expect_counts()],
        )
        add(
            "move tab --position bottom",
            key,
            lambda out: [
                "move", "tab", SOURCES[key], "--id", str(f.tab_ids[0]),
                "--position", "bottom", "-o", out,
            ],
            semantic=[
                expect_counts(),
                expect_tab_titles(
                    [t.get("title") or "" for t in f.tab_list[1:]]
                    + [f.tab_list[0].get("title") or ""]
                ),
            ],
        )
    add(
        "move row --to-tab 2",
        "v2",
        lambda out: [
            "move", "row", SOURCES["v2"], "--id", str(facts["v2"].rows[0]["id"]),
            "--to-tab", "2", "-o", out,
        ],
        semantic=[expect_row_tab(facts["v2"].rows[0]["id"], 2), expect_counts()],
    )

    # ----------------------------------------------------------- estrazione
    for key, f in facts.items():
        if key not in ("classic", "v2"):
            continue
        row = f.rows[0]
        row_id = row["id"]
        panel = f.panels[0]
        pid = panel["id"]
        add(
            "extract panel",
            key,
            lambda out: ["extract", "panel", SOURCES[key], "--id", str(pid), "-o", out],
            semantic=[expect_panel_count(1), expect_identity()],
        )
        add(
            "extract row",
            key,
            lambda out: ["extract", "row", SOURCES[key], "--id", str(row_id), "-o", out],
            semantic=[
                expect_panel_count(
                    len([c for c in model.row_children(f.db, row) if c.get("type") != "row"])
                ),
                expect_identity(),
            ],
        )
        add(
            "extract row v2",
            key,
            lambda out: [
                "extract", "row", SOURCES[key], "--id", str(row_id),
                "--to-format", "v2", "-o", out,
            ],
            semantic=[expect_no_uid()],
        )
    add(
        "extract tab 2",
        "v2",
        lambda out: ["extract", "tab", SOURCES["v2"], "--id", "2", "-o", out],
        semantic=[
            expect_panel_count(len(tabs.panels_of(facts["v2"].db, 2))),
            expect_identity(),
        ],
    )

    # ----------------------------------------------------------------- fork
    for key, f in facts.items():
        if key not in ("classic", "v2"):
            continue
        add(
            "fork",
            key,
            lambda out: ["fork", SOURCES[key], "-o", out],
            semantic=[expect_counts(), expect_ids_contiguous()],
        )
        add(
            "fork --strip-links",
            key,
            lambda out: ["fork", SOURCES[key], "--strip-links", "-o", out],
            semantic=[expect_no_binding("links"), expect_counts()],
        )
        add(
            "fork --keep-library --keep-alerts",
            key,
            lambda out: [
                "fork", SOURCES[key], "--keep-library", "--keep-alerts", "-o", out
            ],
            semantic=[expect_counts()],
        )
    add(
        "fork classic -> v2",
        "classic",
        lambda out: ["fork", SOURCES["classic"], "--to-format", "v2", "-o", out],
        semantic=[expect_counts(), expect_no_uid()],
    )
    add(
        "fork v2 -> classic",
        "v2",
        lambda out: ["fork", SOURCES["v2"], "--to-format", "classic", "-o", out],
        semantic=[expect_counts(), expect_ids_contiguous()],
    )
    add(
        "fork v2 --keep-tab 2",
        "v2",
        lambda out: ["fork", SOURCES["v2"], "--keep-tab", "2", "-o", out],
        semantic=[
            expect_single_tab(),
            expect_panel_count(len(tabs.panels_of(facts["v2"].db, 2))),
            expect_ids_contiguous(),
        ],
    )
    add(
        "fork v2 --keep-tab 1 --to-format classic",
        "v2",
        lambda out: [
            "fork", SOURCES["v2"], "--keep-tab", "1", "--to-format", "classic", "-o", out
        ],
        semantic=[
            expect_panel_count(len(tabs.panels_of(facts["v2"].db, 1))),
            expect_ids_contiguous(),
        ],
    )

    # --------------------------------------------------------------- layout
    for key, f in facts.items():
        if key not in ("classic", "v2"):
            continue
        add(
            "layout",
            key,
            lambda out: ["layout", SOURCES[key], "-o", out],
            semantic=[expect_counts()],
            check_blocks=True,
        )
        add(
            "layout --columns 12",
            key,
            lambda out: ["layout", SOURCES[key], "--columns", "12", "-o", out],
            semantic=[expect_counts()],
            check_blocks=True,
        )
        add(
            "layout --in-row",
            key,
            lambda out: [
                "layout", SOURCES[key], "--in-row", str(f.rows[0]["id"]),
                "--default-width", "8", "--default-height", "6", "-o", out,
            ],
            semantic=[expect_counts()],
        )
        add(
            "layout v2 output",
            key,
            lambda out: ["layout", SOURCES[key], "--to-format", "v2", "-o", out],
            semantic=[expect_counts()],
        )

    # ------------------------------------------------------ casi d'errore
    bad = os.path.join(WORK, "json-non-valido.json")
    array = os.path.join(WORK, "radice-lista.json")
    empty = os.path.join(WORK, "radice-vuota.json")
    with open(bad, "w", encoding="utf-8") as fh:
        fh.write("{ non json")
    with open(array, "w", encoding="utf-8") as fh:
        json.dump([1, 2, 3], fh)
    with open(empty, "w", encoding="utf-8") as fh:
        json.dump({}, fh)

    for key, f in facts.items():
        if key not in ("classic", "v2"):
            continue
        row_id = f.rows[0]["id"]
        panel_id = f.panels[0]["id"]
        tab_id = f.tab_ids[0]
        empty_row = next((r for r in f.rows if not model.row_children(f.db, r)), None)
        add(
            "ERR file inesistente",
            key,
            lambda out: ["validate", os.path.join(WORK, "non-esiste.json")],
            expect="error", output=False, rc=2,
        )
        add(
            "ERR json non valido",
            key,
            lambda out: ["validate", bad],
            expect="error", output=False, rc=2,
        )
        add(
            "ERR radice lista",
            key,
            lambda out: ["validate", array],
            expect="error", output=False, rc=2,
        )
        add(
            "ERR formato sconosciuto",
            key,
            lambda out: ["validate", empty],
            expect="error", output=False, rc=2,
        )
        add(
            "ERR update su formato sconosciuto",
            key,
            lambda out: ["update", "panel", empty, "--id", "1", "--title", "x", "-o", out],
            expect="error", rc=2,
        )
        add(
            "ERR nessuna modifica",
            key,
            lambda out: ["update", "row", SOURCES[key], "--id", str(row_id), "-o", out],
            expect="error", rc=1,
        )
        add(
            "ERR delete senza selettore",
            key,
            lambda out: ["delete", "panel", SOURCES[key], "-o", out],
            expect="error", rc=1,
        )
        add(
            "ERR id inesistente",
            key,
            lambda out: ["list", "panel", SOURCES[key], "--id", "999999"],
            expect="error", output=False, rc=1,
        )
        add(
            "ERR match-type su righe",
            key,
            lambda out: ["list", "row", SOURCES[key], "--match-type", "timeseries"],
            expect="error", output=False, rc=1,
        )
        add(
            "ERR in-tab su tab",
            key,
            lambda out: ["list", "tab", SOURCES[key], "--in-tab", "1"],
            expect="error", output=False, rc=1,
        )
        add(
            "ERR tab inesistente",
            key,
            lambda out: ["list", "panel", SOURCES[key], "--in-tab", "99"],
            expect="error", output=False, rc=1,
        )
        add(
            "ERR tipo sbagliato (row su pannello)",
            key,
            lambda out: ["update", "row", SOURCES[key], "--id", str(panel_id), "--title", "x", "-o", out],
            expect="error", rc=1,
        )
        add(
            "ERR tipo sbagliato (panel su riga)",
            key,
            lambda out: ["update", "panel", SOURCES[key], "--id", str(row_id), "--title", "x", "-o", out],
            expect="error", rc=1,
        )
        add(
            "ERR create panel senza sorgente",
            key,
            lambda out: ["create", "panel", SOURCES[key], "--title", "x", "-o", out],
            expect="error", rc=1,
        )
        add(
            "ERR create panel da una riga",
            key,
            lambda out: [
                "create", "panel", SOURCES[key], "--from-id", str(row_id), "-o", out
            ],
            expect="error", rc=1,
        )
        add(
            "ERR create row con due sorgenti",
            key,
            lambda out: [
                "create", "row", SOURCES[key], "--from-id", str(row_id),
                "--template", "templates/system-view.row.tpl.json", "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR create tab da --from-id",
            key,
            lambda out: ["create", "tab", SOURCES[key], "--from-id", "1", "-o", out],
            expect="error", rc=1,
        )
        add(
            "ERR base-id in collisione",
            key,
            lambda out, bid=f.panels[0]["id"]: [
                "create", "row", SOURCES[key], "--title", "X",
                "--base-id", str(bid), "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR create row tab inesistente",
            key,
            lambda out: [
                "create", "row", SOURCES[key], "--title", "X", "--to-tab", "99", "-o", out
            ],
            expect="error", rc=1,
        )
        add(
            "ERR create panel --to-tab",
            key,
            lambda out: [
                "create", "panel", SOURCES[key], "--from-id", str(panel_id),
                "--to-tab", str(tab_id), "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR move tab --to-tab",
            key,
            lambda out: [
                "move", "tab", SOURCES[key], "--id", str(tab_id),
                "--to-tab", str(tab_id), "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR move row --to-row",
            key,
            lambda out: [
                "move", "row", SOURCES[key], "--id", str(row_id),
                "--to-row", str(row_id), "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR move panel senza destinazione",
            key,
            lambda out: ["move", "panel", SOURCES[key], "--id", str(panel_id), "-o", out],
            expect="error", rc=1,
        )
        add(
            "ERR move panel nella stessa riga",
            key,
            lambda out: [
                "move", "panel", SOURCES[key],
                "--id", str(next(p for _, _, p, r in model.iter_panel_slots(f.db) if r and r.get("id") == row_id)["id"]),
                "--to-row", str(row_id), "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR move row rispetto a se stessa",
            key,
            lambda out: [
                "move", "row", SOURCES[key], "--id", str(row_id),
                "--before", str(row_id), "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR delete panel --keep-children",
            key,
            lambda out: [
                "delete", "panel", SOURCES[key], "--id", str(panel_id),
                "--keep-children", "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR update row --datasource-type senza --datasource",
            key,
            lambda out: [
                "update", "row", SOURCES[key], "--id", str(row_id),
                "--datasource-type", "prometheus", "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR update tab --collapsed",
            key,
            lambda out: [
                "update", "tab", SOURCES[key], "--id", str(tab_id),
                "--collapsed", "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR update panel titolo vuoto",
            key,
            lambda out: [
                "update", "panel", SOURCES[key], "--id", str(panel_id),
                "--title", "   ", "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR fork --uid con uscita v2",
            key,
            lambda out: [
                "fork", SOURCES[key], "--uid", "abc", "--to-format", "v2", "-o", out
            ],
            expect="error", rc=1,
        )
        add(
            "ERR fork --keep-tab inesistente",
            key,
            lambda out: ["fork", SOURCES[key], "--keep-tab", "99", "-o", out],
            expect="error", rc=1,
        )
        add(
            "ERR fork inventario mancante",
            key,
            lambda out: [
                "fork", SOURCES[key], "--existing-dashboards",
                os.path.join(WORK, "non-esiste.json"), "-o", out,
            ],
            expect="error", rc=2,
        )
        add(
            "ERR extract base-id 0",
            key,
            lambda out: [
                "extract", "panel", SOURCES[key], "--id", str(panel_id),
                "--base-id", "0", "-o", out,
            ],
            expect="error", rc=1,
        )
        add(
            "ERR extract multi-selezione",
            key,
            lambda out: [
                "extract", "panel", SOURCES[key], "--match-title", ".*", "-o", out
            ],
            expect="error", rc=1,
        )
        add(
            "ERR layout columns 0",
            key,
            lambda out: ["layout", SOURCES[key], "--columns", "0", "-o", out],
            expect="error", rc=1,
        )
        add(
            "ERR layout in-row inesistente",
            key,
            lambda out: ["layout", SOURCES[key], "--in-row", "999999", "-o", out],
            expect="error", rc=1,
        )
        add(
            "ERR to-format invalido",
            key,
            lambda out: ["validate", SOURCES[key], "--to-format", "boh"],
            expect="error", output=False, rc=2,
        )
        add(
            "ERR severita invalida",
            key,
            lambda out: ["validate", SOURCES[key], "--severity", "boh"],
            expect="error", output=False, rc=2,
        )
        add(
            "ERR regex non valida",
            key,
            lambda out: ["list", "panel", SOURCES[key], "--match-title", "["],
            expect="error", output=False, rc=1,
            semantic=[expect_not_contains("Traceback"), expect_contains("espressione regolare non valida")],
        )
        sev_path = os.path.join(WORK, f"sev-{key}.json")
        renamed = sev_path[: -len(".json")] + "_ERROR_LINT_ERROR.json"
        add(
            "severity warning -> validazione fallita e file rinominato",
            key,
            lambda out, p=sev_path: [
                "update", "panel", SOURCES[key], "--id", str(panel_id),
                "--title", "Titolo", "-o", p, "--severity", "warning",
            ],
            expect="error", output=False, rc=1,
            semantic=[
                expect_file_absent(sev_path),
                expect_file_present(renamed),
                expect_contains("Validazione fallita (lint)"),
            ],
        )
        if len(f.tab_ids) == 1:
            add(
                "ERR delete ultimo tab",
                key,
                lambda out: [
                    "delete", "tab", SOURCES[key], "--id", str(tab_id), "-o", out
                ],
                expect="error", rc=1,
            )

    # output che è una directory
    directory = os.path.join(WORK, "una-directory")
    os.makedirs(directory, exist_ok=True)
    add(
        "ERR output è una directory",
        "classic",
        lambda out, d=directory: [
            "update", "tab", SOURCES["classic"], "--id", "1",
            "--title", "x", "-o", d,
        ],
        expect="error", output=False, rc=3,
    )

    for key, f in facts.items():
        if key in ("classic", "v2"):
            _cases_extra(key, f)


def _cases_extra(key: str, f: Facts) -> None:
    """Combinazioni ulteriori: dry-run, output predefinito, template, opzioni."""
    src = SOURCES[key]
    template_path = os.path.join(ROOT, "templates", "system-view.row.tpl.json")
    with open(template_path, encoding="utf-8") as fh:
        template_panels = len(content(formats.load(copy.deepcopy(json.load(fh))).db))

    titled = next(p for p in f.panels if p.get("title"))
    pid = titled["id"]
    row = f.rows[0]
    row_id = row["id"]
    existing_title = row.get("title") or ""
    children = len(model.row_children(f.db, row))

    # ---------------------------------------------------------- dry-run
    dry = os.path.join(WORK, f"dry-{key}.json")
    add(
        "dry-run update",
        key,
        lambda out: [
            "update", "panel", src, "--id", str(pid), "--title", "X",
            "-o", dry, "--dry-run",
        ],
        output=False,
        semantic=[expect_contains("[dry-run]"), expect_file_absent(dry)],
    )
    add(
        "dry-run fork",
        key,
        lambda out: ["fork", src, "-o", dry + "-fork", "--dry-run"],
        output=False,
        semantic=[expect_contains("[dry-run]"), expect_file_absent(dry + "-fork")],
    )

    # ------------------------------------------------ output predefinito
    copied = os.path.join(WORK, f"default-{key}-input.json")
    shutil.copyfile(src, copied)
    expected = os.path.join(WORK, f"default-{key}-input_out.json")
    add(
        "output predefinito <input>_out.json",
        key,
        lambda out, c=copied: [
            "update", "panel", c, "--id", str(pid), "--title", "Titolo default"
        ],
        output=False,
        semantic=[expect_file_present(expected)],
    )

    # ------------------------------------------------------------- fork
    add(
        "fork --title --uid (classico)",
        key,
        lambda out: [
            "fork", src, "--title", "Copia esplicita", "--uid", "uid-esplicito",
            "--to-format", "classic", "-o", out,
        ],
        semantic=[
            expect_counts(), expect_root(uid="uid-esplicito", title="Copia esplicita")
        ],
    )
    if len(f.tab_ids) == 1:
        add(
            "fork --keep-tab 1 (un solo tab)",
            key,
            lambda out: ["fork", src, "--keep-tab", "1", "-o", out],
            semantic=[expect_counts(), expect_ids_contiguous()],
        )

    # ------------------------------------------------- on-existing
    add(
        "create row --on-existing error",
        key,
        lambda out: [
            "create", "row", src, "--template", "templates/system-view.row.tpl.json",
            "--title", existing_title, "-o", out,
        ],
        expect="error", rc=1,
    )
    add(
        "create row --on-existing skip",
        key,
        lambda out: [
            "create", "row", src, "--template", "templates/system-view.row.tpl.json",
            "--title", existing_title, "--on-existing", "skip", "-o", out,
        ],
        semantic=[expect_counts()],
    )
    add(
        "create row --on-existing append",
        key,
        lambda out: [
            "create", "row", src, "--template", "templates/system-view.row.tpl.json",
            "--title", existing_title, "--on-existing", "append", "-o", out,
        ],
        semantic=[expect_counts(delta_rows=1, delta_panels=template_panels)],
        check_rows=False,
    )
    add(
        "create row --on-existing replace",
        key,
        lambda out: [
            "create", "row", src, "--template", "templates/system-view.row.tpl.json",
            "--title", existing_title, "--on-existing", "replace", "-o", out,
        ],
        semantic=[
            expect_counts(delta_rows=0, delta_panels=template_panels - children),
            expect_single_tab() if key == "classic" else (lambda ctx: []),
        ],
        check_rows=False,
    )

    # -------------------------------------------- template e segnaposto
    params = os.path.join(WORK, "params.json")
    with open(params, "w", encoding="utf-8") as fh:
        json.dump({"NAMESPACE": "namespace-da-file"}, fh)
    add(
        "create row --template --params",
        key,
        lambda out: [
            "create", "row", src, "--template", "templates/system-view.row.tpl.json",
            "--title", "Da params", "--params", params, "-o", out,
        ],
        semantic=[expect_counts(delta_rows=1, delta_panels=template_panels)],
    )
    add(
        "create row segnaposto da CLI",
        key,
        lambda out: [
            "create", "row", src, "--template", "templates/system-view.row.tpl.json",
            "--title", "Da CLI", "--namespace", "ns-cli", "--cluster-gen", "9",
            "--datasource-uid", "ds-cli", "--title-prefix", "pre",
            "--namespace-exact", "-o", out,
        ],
        semantic=[expect_counts(delta_rows=1, delta_panels=template_panels)],
    )
    add(
        "create panel --template",
        key,
        lambda out: [
            "create", "panel", src, "--template", "templates/system-view.row.tpl.json",
            "--title", "Pannello da template", "--to-row", str(row_id), "-o", out,
        ],
        semantic=[expect_counts(delta_panels=1)],
        check_rows=False,
    )
    add(
        "create row --position top",
        key,
        lambda out: [
            "create", "row", src, "--title", "In cima", "--position", "top", "-o", out
        ],
        semantic=[expect_counts(delta_rows=1, delta_panels=template_panels)],
        check_rows=False,
    )
    add(
        "create row --base-id libero",
        key,
        lambda out: [
            "create", "row", src, "--title", "Con base", "--base-id", "5000", "-o", out
        ],
        semantic=[
            expect_counts(delta_rows=1, delta_panels=template_panels),
            # in v2 le righe non hanno id: il primo id è quello del primo figlio
            expect_ids_include(5000 if f.fmt == schema.CLASSIC else 5001),
        ],
        check_rows=False,
    )
    add(
        "create panel --from-id --position top",
        key,
        lambda out: [
            "create", "panel", src, "--from-id", str(pid), "--title", "Sopra",
            "--position", "top", "-o", out,
        ],
        semantic=[expect_counts(delta_panels=1)],
        check_rows=False,
    )

    # ------------------------------------------------ spostamenti relativi
    by_row: dict[int, list[dict[str, Any]]] = {}
    for _, _, panel, owner in model.iter_panel_slots(f.db):
        if owner is not None and panel.get("type") != "row":
            by_row.setdefault(owner["id"], []).append(panel)
    first_row = next(rid for rid, panels in by_row.items() if len(panels) >= 2)
    p1, p2 = by_row[first_row][0], by_row[first_row][1]
    other_row, other_panels = next(
        (rid, panels) for rid, panels in by_row.items() if rid != first_row and panels
    )
    add(
        "move panel --before (stessa riga)",
        key,
        lambda out: [
            "move", "panel", src, "--id", str(p2["id"]),
            "--before", str(p1["id"]), "-o", out,
        ],
        semantic=[expect_row_panel_order(first_row, p2["id"], p1["id"]), expect_counts()],
        check_rows=False,
    )
    add(
        "move panel --after (altra riga)",
        key,
        lambda out: [
            "move", "panel", src, "--id", str(p1["id"]),
            "--after", str(other_panels[0]["id"]), "-o", out,
        ],
        semantic=[
            expect_row_parent(p1["id"], other_row),
            expect_row_panel_order(
                other_row, other_panels[0]["id"], p1["id"]
            ),
            expect_counts(),
        ],
        check_rows=False,
    )
    add(
        "move row --after",
        key,
        lambda out: [
            "move", "row", src, "--id", str(f.rows[0]["id"]),
            "--after", str(f.rows[1]["id"]), "-o", out,
        ],
        semantic=[
            expect_row_titles_order(
                [f.rows[1].get("title") or "", f.rows[0].get("title") or ""]
                + [r.get("title") or "" for r in f.rows[2:]]
            ),
            expect_counts(),
        ],
    )
    add(
        "ERR move panel --before inesistente",
        key,
        lambda out: [
            "move", "panel", src, "--id", str(p1["id"]),
            "--before", "999999", "-o", out,
        ],
        expect="error", rc=1,
    )
    if len(f.tab_ids) == 2:
        t1, t2 = [t.get("title") or "" for t in f.tab_list]
        add(
            "move tab --id 2 --before 1",
            "v2",
            lambda out: ["move", "tab", SOURCES["v2"], "--id", "2", "--before", "1", "-o", out],
            semantic=[expect_tab_titles([t2, t1]), expect_counts()],
        )
        add(
            "move tab --id 1 --after 2",
            "v2",
            lambda out: ["move", "tab", SOURCES["v2"], "--id", "1", "--after", "2", "-o", out],
            semantic=[expect_tab_titles([t2, t1]), expect_counts()],
        )

    # ---------------------------------------------------------- extract
    add(
        "extract panel con titolo, uid e base-id",
        key,
        lambda out: [
            "extract", "panel", src, "--id", str(pid), "--title", "Estratto",
            "--uid", "uid-extra", "--base-id", "900",
            "--to-format", "classic", "-o", out,
        ],
        semantic=[
            expect_panel_count(1),
            expect_root(uid="uid-extra", title="Estratto"),
            expect_first_id(900),
        ],
    )
    add(
        "extract panel --uid con uscita v2 (uid dichiarato perso)",
        key,
        lambda out: [
            "extract", "panel", src, "--id", str(pid), "--uid", "uid-extra",
            "--to-format", "v2", "-o", out,
        ],
        semantic=[expect_no_uid(), expect_panel_count(1)],
    )
    add(
        "extract panel con inventario",
        key,
        lambda out: [
            "extract", "panel", src, "--id", str(pid), "--existing-dashboards",
            os.path.join(SYNTH, "inventario.json"), "-o", out,
        ],
        semantic=[expect_identity(), expect_panel_count(1)],
    )

    # --------------------------------------------------- multi-selezione
    n_text = len([p for p in f.panels if p.get("type") == "text"])
    if n_text:
        add(
            "delete panel --match-type text",
            key,
            lambda out: ["delete", "panel", src, "--match-type", "text", "-o", out],
            semantic=[expect_counts(delta_panels=-n_text)],
        )
    data_panel = next(p for p in f.panels if p.get("targets"))
    timeseries = next(
        (
            p for p in f.panels
            if p.get("type") == "timeseries" and p.get("targets")
        ),
        data_panel,
    )
    first_expr = next(
        (
            t.get("expr")
            for t in timeseries.get("targets") or []
            if isinstance(t, dict) and isinstance(t.get("expr"), str)
        ),
        "",
    )
    token = (re.findall(r"[A-Za-z_][A-Za-z0-9_]{5,}", first_expr) or ["sum"])[0]
    add(
        "update panel --match-type timeseries --replace",
        key,
        lambda out, tok=token: [
            "update", "panel", src, "--match-type", "timeseries",
            "--replace", f"{tok}={tok}_v2", "-o", out,
        ],
        semantic=[expect_expr_contains(f"{token}_v2"), expect_counts()],
    )
    add(
        "list panel --format json --match-title",
        key,
        lambda out: [
            "list", "panel", src, "--match-title", ".*", "--format", "json"
        ],
        output=False,
        semantic=[expect_json_stdout()],
    )

    # ------------------------------------------------------------- layout
    add(
        "layout --default-width --default-height",
        key,
        lambda out: [
            "layout", src, "--default-width", "8", "--default-height", "6", "-o", out
        ],
        semantic=[expect_counts()],
        check_blocks=True,
    )
    expanded = next((r for r in f.rows if r.get("collapsed") is False), None)
    if expanded is not None:
        add(
            "layout --in-row su riga espansa",
            key,
            lambda out: [
                "layout", src, "--in-row", str(expanded["id"]), "-o", out
            ],
            semantic=[expect_counts()],
        )

    # ------------------------------------------------- in-tab e selezione
    if len(f.tab_ids) == 2:
        add(
            "update row --in-tab 2",
            "v2",
            lambda out: [
                "update", "row", SOURCES["v2"], "--in-tab", "2",
                "--id", str(f.rows[-1]["id"]), "--title", "Solo tab 2", "-o", out,
            ],
            semantic=[expect_row_title(f.rows[-1]["id"], "Solo tab 2"), expect_counts()],
        )
        add(
            "delete panel --in-tab 2",
            "v2",
            lambda out, target_panel=tabs.panels_of(FACTS["v2"].db, 2)[0]["id"]: [
                "delete", "panel", SOURCES["v2"], "--in-tab", "2",
                "--id", str(target_panel), "-o", out,
            ],
            semantic=[expect_counts(delta_panels=-1)],
        )
    add(
        "extract tab (unico tab)",
        key,
        lambda out: [
            "extract", "tab", src, "--id", str(f.tab_ids[0]), "-o", out
        ],
        semantic=[
            expect_panel_count(len(tabs.panels_of(f.db, f.tab_ids[0]))),
            expect_identity(),
        ],
    )
    add(
        "ERR match-title senza risultati",
        key,
        lambda out: [
            "update", "panel", src, "--match-title", "titolo-che-non-esiste-xyz",
            "--title", "X", "-o", out,
        ],
        expect="error", rc=1,
    )


# ------------------------------------------------------------ sorgenti sintetiche


def build_synthetic(facts: dict[str, Facts]) -> dict[str, Facts]:
    """Dashboard derivate dal classico con alert e pannello di libreria."""
    os.makedirs(SYNTH, exist_ok=True)
    made: dict[str, Facts] = {}

    base = load_facts("classic", SOURCES["classic"])

    def write(name: str, mutate: Callable[[dict[str, Any]], None]) -> Facts:
        db = copy.deepcopy(base.db)
        mutate(db)
        document, _ = formats.render(db, schema.CLASSIC)
        path = os.path.join(SYNTH, f"{name}.json")
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(document, fh, indent=2, ensure_ascii=False)
        result = load_facts(name, path)
        facts[name] = result
        return result

    def add_alert(db: dict[str, Any]) -> None:
        panel = next(p for p in content(db) if p.get("targets"))
        panel["alert"] = {"name": "Alert di prova", "conditions": []}
        panel["alertId"] = 1

    def add_library(db: dict[str, Any]) -> None:
        panel = content(db)[0]
        panel["libraryPanel"] = {"uid": "lib-001", "name": "Pannello condiviso"}

    made["alert"] = write("alert", add_alert)
    made["library"] = write("library", add_library)

    def drop_datasource(db: dict[str, Any]) -> None:
        panel = next(p for p in content(db) if p.get("targets"))
        panel.pop("datasource", None)
        for target in panel.get("targets") or []:
            if isinstance(target, dict):
                target.pop("datasource", None)

    made["nodataset"] = write("nodataset", drop_datasource)
    bare = next(p for p in made["nodataset"].panels if p.get("targets"))
    add(
        "update panel --datasource senza --datasource-create",
        "nodataset",
        lambda out: [
            "update", "panel", made["nodataset"].path, "--id", str(bare["id"]),
            "--datasource", "NUOVO-UID", "-o", out,
        ],
        semantic=[expect_no_datasource(bare["id"]), expect_counts()],
    )
    add(
        "update panel --datasource-create",
        "nodataset",
        lambda out: [
            "update", "panel", made["nodataset"].path, "--id", str(bare["id"]),
            "--datasource", "NUOVO-UID", "--datasource-create", "-o", out,
        ],
        semantic=[expect_datasource("NUOVO-UID", bare["id"]), expect_counts()],
    )

    alert_panel = next(p for p in made["alert"].panels if p.get("alert"))
    lib_panel = next(p for p in made["library"].panels if p.get("libraryPanel"))

    add(
        "alert -> v2 senza --drop-alerts",
        "alert",
        lambda out: ["update", "panel", made["alert"].path, "--id", str(alert_panel["id"]),
                     "--title", str(alert_panel.get("title") or ""), "--to-format", "v2", "-o", out],
        expect="error", rc=2,
    )
    add(
        "alert -> v2 con --drop-alerts",
        "alert",
        lambda out: ["update", "panel", made["alert"].path, "--id", str(alert_panel["id"]),
                     "--title", str(alert_panel.get("title") or ""), "--to-format", "v2",
                     "--drop-alerts", "-o", out],
        semantic=[expect_no_binding("alert")],
        check_blocks=False,
    )
    add(
        "fork alert rimuove le regole",
        "alert",
        lambda out: ["fork", made["alert"].path, "-o", out],
        semantic=[expect_no_binding("alert"), expect_ids_contiguous()],
    )
    add(
        "fork alert --keep-alerts",
        "alert",
        lambda out: ["fork", made["alert"].path, "--keep-alerts", "-o", out],
        semantic=[expect_has_binding("alert")],
    )
    add(
        "ERR fork alert --keep-alerts -> v2",
        "alert",
        lambda out: ["fork", made["alert"].path, "--keep-alerts", "--to-format", "v2", "-o", out],
        expect="error", rc=2,
    )
    add(
        "fork library rimuove il riferimento",
        "library",
        lambda out: ["fork", made["library"].path, "-o", out],
        semantic=[expect_no_binding("library")],
    )
    add(
        "fork library --keep-library",
        "library",
        lambda out: ["fork", made["library"].path, "--keep-library", "-o", out],
        semantic=[expect_has_binding("library"), expect_contains("SHARED_LIBRARY_PANEL")],
    )
    add(
        "fork library --keep-library -> v2",
        "library",
        lambda out: [
            "fork", made["library"].path, "--keep-library", "--to-format", "v2", "-o", out
        ],
        semantic=[expect_has_binding("library"), expect_no_uid()],
    )
    add(
        "fork library -> v2 stacca il riferimento",
        "library",
        lambda out: [
            "fork", made["library"].path, "--to-format", "v2", "-o", out
        ],
        semantic=[expect_no_binding("library"), expect_no_uid()],
    )
    add(
        "fork con inventario",
        "classic",
        lambda out: [
            "fork", SOURCES["classic"], "--existing-dashboards",
            os.path.join(SYNTH, "inventario.json"), "-o", out,
        ],
        semantic=[expect_identity()],
    )
    return made


def write_inventory() -> None:
    payload = [
        {"uid": "bTRpcsCvk", "title": "PA-DIGITAL(GEN3) - WEBCHECKUP"},
        {"uid": "altro-uid", "title": "NESB Overview Gen2/Gen3"},
    ]
    with open(os.path.join(SYNTH, "inventario.json"), "w", encoding="utf-8") as fh:
        json.dump(payload, fh, indent=2)


# ------------------------------------------------------------------ runner


@dataclass
class Outcome:
    name: str
    src: str
    argv: list[str]
    code: int
    status: str          # PASS | FAIL | WARN
    problems: list[str]
    stdout: str
    stderr: str


def parse_output(path: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        with open(path, encoding="utf-8") as fh:
            raw = json.load(fh)
    except (OSError, json.JSONDecodeError) as exc:
        return None, [f"output illeggibile: {exc}"]
    if not isinstance(raw, dict):
        return None, ["output non è un oggetto JSON"]
    return raw, []


def expected_format(case: Case, argv: list[str]) -> str:
    if "--to-format" in argv:
        return argv[argv.index("--to-format") + 1]
    return FACTS[case.src].fmt


def execute(index: int, case: Case, facts: dict[str, Facts]) -> Outcome:
    out_path: str | None = None
    if case.output:
        out_path = os.path.join(WORK, f"{index:03d}-{slug(case.name)}.json")
        if os.path.exists(out_path):
            os.remove(out_path)
    argv = case.args(out_path)

    logs_before = set(os.listdir(LOGS)) if os.path.isdir(LOGS) else set()
    result = run(argv)
    logs_after = set(os.listdir(LOGS)) if os.path.isdir(LOGS) else set()
    new_logs = logs_after - logs_before

    problems: list[str] = []

    if case.expect == "error":
        if result.code == 0:
            problems.append("exit 0, atteso un errore")
        if case.rc is not None and result.code != case.rc:
            problems.append(f"exit {result.code}, atteso {case.rc}")
        if not (result.out.strip() or result.err.strip()):
            problems.append("nessun messaggio d'errore")
        if out_path and os.path.exists(out_path):
            problems.append("file di output scritto nonostante l'errore")
        if result.code in (1, 2, 3) and not new_logs:
            problems.append("nessun log in out/")
        ctx = Ctx(
            case=case,
            facts=facts[case.src],
            out_path=None,
            out_raw=None,
            out_db=None,
            run=result,
            expected_format=expected_format(case, argv),
        )
        for check in case.semantic:
            problems.extend(check(ctx))
        status = "PASS" if not problems else "FAIL"
        return Outcome(case.name, case.src, argv, result.code, status, problems,
                       result.out, result.err)

    if result.code != 0:
        problems.append(f"exit {result.code} (atteso 0)")
        status = "FAIL"
        return Outcome(case.name, case.src, argv, result.code, status, problems,
                       result.out, result.err)

    if not case.output:
        # comandi read-only o dry-run: nessun file, ma le verifiche sul
        # messaggio (es. JSON su stdout) vanno comunque eseguite.
        ctx = Ctx(
            case=case,
            facts=facts[case.src],
            out_path=None,
            out_raw=None,
            out_db=None,
            run=result,
            expected_format=expected_format(case, argv),
        )
        for check in case.semantic:
            problems.extend(check(ctx))
        status = "PASS" if not problems else "FAIL"
        return Outcome(case.name, case.src, argv, result.code, status, problems,
                       result.out, result.err)

    raw, parse_problems = parse_output(out_path)  # type: ignore[arg-type]
    problems.extend(parse_problems)
    if raw is None:
        return Outcome(case.name, case.src, argv, result.code, "FAIL", problems,
                       result.out, result.err)

    try:
        out_db = formats.load(copy.deepcopy(raw)).db
    except Exception as exc:  # noqa: BLE001
        problems.append(f"output non rileggibile: {type(exc).__name__}: {exc}")
        return Outcome(case.name, case.src, argv, result.code, "FAIL", problems,
                       result.out, result.err)

    ctx = Ctx(
        case=case,
        facts=facts[case.src],
        out_path=out_path,
        out_raw=raw,
        out_db=out_db,
        run=result,
        expected_format=expected_format(case, argv),
        check_blocks=case.check_blocks,
        check_rows=case.check_rows,
    )
    problems.extend(generic_checks(ctx))
    problems.extend(variable_checks(ctx))
    for check in case.semantic:
        problems.extend(check(ctx))

    status = "PASS" if not problems else "FAIL"
    return Outcome(case.name, case.src, argv, result.code, status, problems,
                   result.out, result.err)


def run_all() -> tuple[list[Outcome], bool]:
    """Esegue tutta la matrice, scrive il report e ritorna gli esiti.

    Il secondo valore dice se i file di input sono rimasti intatti. La
    funzione non stampa e non esce: la usano sia la CLI sia il test della
    suite (`tests/matrix/test_matrix.py`).
    """
    if os.path.isdir(WORK):
        shutil.rmtree(WORK)
    os.makedirs(WORK)
    os.makedirs(LOGS)
    os.makedirs(SYNTH)
    os.environ["GRAFANA_TOOL_LOG_DIR"] = LOGS

    facts = {key: load_facts(key, path) for key, path in SOURCES.items()}
    FACTS.clear()
    FACTS.update(facts)
    CASES.clear()
    OUTCOMES.clear()
    write_inventory()

    def digest(path: str) -> str:
        import hashlib

        with open(path, "rb") as fh:
            return hashlib.sha256(fh.read()).hexdigest()

    before = {key: digest(path) for key, path in SOURCES.items()}

    build_cases(FACTS)
    build_synthetic(FACTS)

    outcomes: list[Outcome] = list(OUTCOMES)

    after = {key: digest(path) for key, path in SOURCES.items()}
    untouched = before == after
    write_report(outcomes, untouched)
    return outcomes, untouched


def main() -> int:
    outcomes, untouched = run_all()
    passed = sum(1 for o in outcomes if o.status == "PASS")
    failed = [o for o in outcomes if o.status == "FAIL"]

    print(f"Casi eseguiti: {len(outcomes)}")
    print(f"  PASS: {passed}")
    print(f"  FAIL: {len(failed)}")
    print(f"  sorgenti intatte: {'sì' if untouched else 'NO'}")
    print(f"  report: {REPORT_MD}")
    if failed:
        print("\nFallimenti:")
        for outcome in failed:
            print(f"- [{outcome.src}] {outcome.name} (exit {outcome.code})")
            for problem in outcome.problems:
                print(f"    {problem}")

    return 0 if not failed and untouched else 1


def write_report(outcomes: list[Outcome], untouched: bool) -> None:
    passed = [o for o in outcomes if o.status == "PASS"]
    failed = [o for o in outcomes if o.status == "FAIL"]
    lines = [
        "# Matrice comandi × parametri",
        "",
        "Sorgenti: `dashboard-classic.json`, `dashboard-v2.json` e tre derivate "
        "(con alert, con pannello di libreria, senza datasource).",
        "",
        f"- casi eseguiti: **{len(outcomes)}**",
        f"- passati: **{len(passed)}**",
        f"- falliti: **{len(failed)}**",
        f"- sorgenti intatte: **{'sì' if untouched else 'no'}**",
        "",
        "## Criteri verificati su ogni file prodotto",
        "",
        "1. JSON oggetto, nel formato atteso (`--to-format` o quello d'ingresso).",
        "2. Nessuna chiave interna (`_tabs`, `_tab`, `_element`, `_extras`, `_relative_grid`).",
        "3. Rileggibile dal tool; id interi, unici; ogni riga in un tab esistente.",
        "4. In v2 ogni elemento collocato una sola volta e nessun riferimento pendente.",
        "5. Variabili identiche (nome, valore, query, datasource); `hide` azzerato "
        "salvo `--keep-variable-visibility`.",
        "6. Nessun matcher con valore fisso omonimo di una variabile salvo "
        "`--keep-literal-values`.",
        "7. Pannelli della stessa riga senza sovrapposizioni; blocchi di primo "
        "livello senza sovrapposizioni dove il comando ricalcola la griglia.",
        "8. Validazione strutturale e lint senza errori.",
        "9. Conteggi di righe, pannelli e query preservati dai comandi che non "
        "li cambiano; file d'ingresso mai modificato.",
        "",
    ]
    if failed:
        lines += ["## Fallimenti", ""]
        for outcome in failed:
            lines.append(f"### {outcome.name}")
            lines.append("")
            lines.append(f"- sorgente: `{outcome.src}`")
            lines.append(f"- exit: {outcome.code}")
            lines.append(f"- comando: `grafana-utils {' '.join(outcome.argv)}`")
            for problem in outcome.problems:
                lines.append(f"- **{problem}**")
            lines.append("")
    else:
        lines += ["Nessun fallimento.", ""]

    lines += ["## Tutti i casi", "", "| caso | sorgente | exit | esito |", "| --- | --- | --- | --- |"]
    for outcome in outcomes:
        lines.append(f"| {outcome.name} | {outcome.src} | {outcome.code} | {outcome.status} |")

    with open(REPORT_MD, "w", encoding="utf-8") as fh:
        fh.write("\n".join(lines) + "\n")
    with open(REPORT_JSON, "w", encoding="utf-8") as fh:
        json.dump(
            [
                {
                    "name": o.name,
                    "source": o.src,
                    "argv": o.argv,
                    "exit": o.code,
                    "status": o.status,
                    "problems": o.problems,
                }
                for o in outcomes
            ],
            fh,
            indent=2,
            ensure_ascii=False,
        )


if __name__ == "__main__":
    sys.exit(main())
