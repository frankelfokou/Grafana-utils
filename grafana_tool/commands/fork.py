"""fork: copia l'intera dashboard in una nuova, senza legami con l'originale.

`extract` prende una riga o un pannello e ne fa una dashboard minima. `fork`
prende tutto e ne fa una dashboard *nuova*: è l'operazione che serve quando
si vuole una copia su cui lavorare senza toccare quella vera.

Tre cose rendono una copia davvero nuova:

  - **identità**: uid diverso, `id` nullo e `version` 1, così Grafana crea
    una dashboard invece di aggiornare l'originale;
  - **numerazione**: gli id dei pannelli ripartono da 1, così nessuno dei
    numeri della sorgente sopravvive;
  - **vincoli**: i riferimenti a libreria e le regole di alert vengono
    staccati, perché continuerebbero a puntare a oggetti e a destinatari
    della dashboard originale.

I link restano: fanno parte del contenuto. Si rimuovono solo con
`--strip-links`.
"""
from __future__ import annotations

import argparse

from grafana_tool import identity, schema, tabs
from grafana_tool.cli_common import add_title_option
from grafana_tool.command_base import WriteCommand
from grafana_tool.identity import detach_bindings, renumber_dashboard, seal_new_dashboard
from grafana_tool.io import load_json
from grafana_tool.model import iter_all_panels


class ForkCommand(WriteCommand):
    NAME = "fork"
    HELP = "Copia la dashboard in una nuova, senza identità né vincoli della precedente"

    def add_arguments(self, parser: argparse.ArgumentParser) -> None:
        add_title_option(parser, "Titolo della nuova dashboard (default: quello attuale, reso unico)")
        parser.add_argument(
            "--uid",
            help="uid della nuova dashboard (default: generato, verificato contro l'inventario)",
        )
        parser.add_argument(
            "--existing-dashboards", dest="existing_dashboards", metavar="FILE",
            help=(
                "Inventario JSON delle dashboard già presenti in Grafana "
                "(lista di {uid,title} o risposta di GET /api/search)"
            ),
        )
        parser.add_argument(
            "--keep-library", dest="keep_library", action="store_true",
            help="Mantieni i riferimenti ai pannelli di libreria (default: staccati)",
        )
        parser.add_argument(
            "--keep-alerts", dest="keep_alerts", action="store_true",
            help="Mantieni le regole di alert legacy (default: rimosse)",
        )
        parser.add_argument(
            "--strip-links", dest="strip_links", action="store_true",
            help="Rimuovi anche i link della dashboard (default: conservati)",
        )
        parser.add_argument(
            "--keep-tab", dest="keep_tab", type=int, metavar="N",
            help=(
                "Duplica solo il tab N e scarta gli altri. Senza questo flag una "
                "copia classica appiattisce tutti i tab e prefissa i titoli"
            ),
        )

    def _inventory(self, args: argparse.Namespace) -> tuple[set[str], set[str]]:
        """uid e titoli delle dashboard già presenti in Grafana, se indicati."""
        if not args.existing_dashboards:
            return set(), set()
        return identity.parse_inventory(load_json(args.existing_dashboards))

    def _taken(self, db: dict, args: argparse.Namespace) -> tuple[set[str], set[str]]:
        """Identità già occupate: inventario più la dashboard di partenza.

        La sorgente esiste ancora, quindi il suo uid e il suo titolo non sono
        liberi: la copia deve avere un nome diverso.
        """
        inv_uids, inv_titles = self._inventory(args)
        taken_uids, taken_titles = set(inv_uids), set(inv_titles)
        identity.extend_text(taken_uids, db.get("uid"))
        identity.extend_text(taken_titles, db.get("title"))
        return taken_uids, taken_titles

    def _keep_only_tab(self, db: dict, tab_id: int) -> tuple[dict, int]:
        """Scarta tutti i tab tranne quello indicato.

        L'eliminazione è dichiarata: il comando stampa quanti tab e quanti
        pannelli sono stati scartati. In uscita classica è l'alternativa
        all'appiattimento: si tiene un tab solo, quindi i titoli restano
        quelli originali, senza prefisso.
        """
        kept = tabs.require(db, tab_id)
        others = [tab for tab in tabs.all_tabs(db) if tab.get("id") != tab_id]
        removed_panels = 0
        for tab in others:
            removed_panels += tabs.remove(db, tab["id"])
        return kept, removed_panels

    def modify(self, db: dict, args: argparse.Namespace) -> dict:
        target = getattr(args, "target_format", schema.CLASSIC)
        if target == schema.V2 and args.uid is not None:
            raise ValueError(
                "--uid non ha effetto con l'uscita v2: lo schema non prevede "
                "l'uid della dashboard. Usa --to-format classic."
            )

        kept_tab = None
        discarded = 0
        if args.keep_tab is not None:
            kept_tab, discarded = self._keep_only_tab(db, args.keep_tab)

        counts = detach_bindings(
            db,
            keep_library=args.keep_library,
            keep_alerts=args.keep_alerts,
            strip_links=args.strip_links,
        )
        total = renumber_dashboard(db)

        # Un fork non eredita i nomi degli elementi v2: seguono i nuovi id.
        for panel in iter_all_panels(db):
            panel.pop("_element", None)

        taken_uids, taken_titles = self._taken(db, args)
        ident = seal_new_dashboard(
            db,
            uid=args.uid,
            title=args.title,
            taken_uids=taken_uids,
            taken_titles=taken_titles,
            identify=target != schema.V2,
        )

        print(f"Dashboard duplicata: {total} oggetti rinumerati da 1.")
        if kept_tab is not None:
            print(
                f"  Solo il tab '{kept_tab.get('title') or ''}': "
                f"scartati gli altri con {discarded} pannelli."
            )
        if counts["library"]:
            print(f"  Riferimenti a pannelli di libreria staccati: {counts['library']}.")
        if counts["alerts"]:
            print(f"  Regole di alert rimosse: {counts['alerts']}.")
        if counts["links"]:
            print(f"  Link rimossi: {counts['links']}.")
        if target == schema.V2:
            print(
                "Dashboard v2: nessun uid assegnato, lo schema non lo prevede."
            )
        else:
            print(f"Identità assegnata: uid '{ident.uid}', id nullo, version 1.")
        print(f"Titolo della nuova dashboard: '{ident.title}'.")
        return db


command = ForkCommand()
