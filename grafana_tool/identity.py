"""identity: assegnare identità nuove agli oggetti scritti in output (SRP).

Responsabilità unica: decidere *chi è* un oggetto quando finisce in un file
di output, senza leggere né scrivere file e senza conoscere argparse.

Tre livelli di identità in Grafana, e come vengono trattati qui:

  - **dashboard**: `uid` è globale nell'istanza; `id` è il numero interno del
    database. Una bozza di dashboard nuova viaggia con `id: null`, `uid`
    generato e `version: 1`, così Grafana la crea e non aggiorna quella
    esistente con lo stesso uid.
  - **pannello**: l'`id` è un intero unico *dentro* la dashboard. Non esiste
    un id di pannello globale: per non riusare i numeri della sorgente i
    comandi che creano pannelli partono da `max + 1` o da una base esplicita.
  - **titolo**: è un'etichetta, non una chiave. Grafana accetta titoli
    duplicati, ma due pannelli con lo stesso nome nella stessa dashboard
    rendono ricerca e link ambigui: `unique_title` aggiunge ` (2)`, ` (3)`.

Le funzioni sono pure: ricevono i valori già presenti in Grafana (inventario
delle dashboard, titoli della dashboard) e restituiscono i nuovi valori.
"""
from __future__ import annotations

import secrets
import string
from typing import Any, Iterable, NamedTuple

from grafana_tool.model import (
    dashboard_roots,
    iter_all_panels,
    iter_panels,
    renumber_ids,
)

# Grafana usa uid alfanumerici di 9 caratteri; lo stesso alfabeto evita uid
# che il server dovrebbe riscrivere.
UID_ALPHABET = string.ascii_letters + string.digits
UID_LENGTH = 9


class DashboardIdentity(NamedTuple):
    """Identità assegnata a una dashboard di output."""

    uid: str
    title: str


def new_uid(length: int = UID_LENGTH) -> str:
    """Genera un uid casuale nello stile di Grafana."""
    if length < 1:
        raise ValueError("La lunghezza dell'uid deve essere positiva.")
    return "".join(secrets.choice(UID_ALPHABET) for _ in range(length))


def new_uid_not_in(taken: Iterable[str], length: int = UID_LENGTH) -> str:
    """Genera un uid che non compare in `taken` (confronto case-insensitive)."""
    used = _folded(taken)
    while True:
        candidate = new_uid(length)
        if candidate.casefold() not in used:
            return candidate


def text_or_empty(value: Any) -> str:
    """Stringa ripulita, oppure `""` se il valore non è testo."""
    return value.strip() if isinstance(value, str) else ""


def extend_text(target: set[str], value: Any) -> None:
    """Aggiunge `value` a `target` se è testo non vuoto."""
    text = text_or_empty(value)
    if text:
        target.add(text)


def _folded(values: Iterable[str]) -> set[str]:
    """Insieme dei valori non vuoti in forma case-insensitive."""
    return {str(v).casefold() for v in values if v}


def _normalized(values: Iterable[str]) -> set[str]:
    """Insieme dei titoli non vuoti in forma di confronto."""
    return {normalize_title(v) for v in values if v}


def normalize_title(title: Any) -> str:
    """Forma di confronto di un titolo: spazi compattati, case-insensitive."""
    return " ".join(str(title or "").split()).casefold()


def unique_title(base: str, taken: Iterable[str], start: int = 2) -> str:
    """Restituisce `base` se libero, altrimenti `base (n)` con n minimo libero."""
    clean = " ".join(str(base or "").split()) or "Senza titolo"
    used = _normalized(taken)
    if normalize_title(clean) not in used:
        return clean
    n = start
    while normalize_title(f"{clean} ({n})") in used:
        n += 1
    return f"{clean} ({n})"


def all_titles(db: dict[str, Any]) -> list[str]:
    """Titoli non vuoti di righe e pannelli della dashboard."""
    out: list[str] = []
    for p in iter_all_panels(db):
        t = p.get("title")
        if isinstance(t, str) and t.strip():
            out.append(t)
    return out


def dedupe_panel_titles(
    panels: Iterable[dict[str, Any]], taken: Iterable[str] = ()
) -> int:
    """Rende unici i titoli dei pannelli (anche annidati) rispetto a `taken`.

    Le righe sono escluse: il loro titolo viene gestito dal comando che le
    crea. I pannelli senza titolo restano senza. Ritorna quanti titoli sono
    stati riscritti.
    """
    used = _normalized(taken)
    renamed = 0
    for p in panels:
        for sub in iter_panels([p]):
            if sub.get("type") == "row":
                continue
            title = sub.get("title")
            if not isinstance(title, str) or not title.strip():
                continue
            new = unique_title(title, used)
            used.add(normalize_title(new))
            if new != title:
                sub["title"] = new
                renamed += 1
    return renamed


def parse_inventory(data: Any) -> tuple[set[str], set[str]]:
    """Estrae `(uid, titoli)` da un inventario di dashboard già esistenti.

    Accetta:
      - la risposta di `GET /api/search` (lista di oggetti con `uid`/`title`);
      - `{"dashboards": [...]}`;
      - una singola dashboard (oggetto con `uid`/`title`).
    """
    if isinstance(data, list):
        items = data
    elif isinstance(data, dict) and isinstance(data.get("dashboards"), list):
        items = data["dashboards"]
    elif isinstance(data, dict):
        items = [data]
    else:
        raise ValueError("Inventario non valido: attesa una lista o un oggetto JSON.")

    uids: set[str] = set()
    titles: set[str] = set()
    for item in items:
        if not isinstance(item, dict):
            continue
        extend_text(uids, item.get("uid"))
        extend_text(titles, item.get("title"))
    return uids, titles


def seal_new_dashboard(
    db: dict[str, Any],
    *,
    uid: str | None = None,
    title: str | None = None,
    taken_uids: Iterable[str] = (),
    taken_titles: Iterable[str] = (),
    identify: bool = True,
) -> DashboardIdentity:
    """Rende `db` una dashboard *nuova* per Grafana.

    - `uid`: quello richiesto, se libero; altrimenti generato e verificato
      contro `taken_uids`. Un uid esplicito già in uso è un errore: non è
      possibile "indovinare" un altro identificativo richiesto dall'utente.
    - `id`: None, così Grafana crea una nuova dashboard.
    - `version`: 1, coerente con una dashboard appena creata.
    - `title`: quello richiesto o quello corrente, reso unico rispetto a
      `taken_titles` con il suffisso ` (2)`, ` (3)`.

    Con `identify=False` vengono saltati uid, id e version: lo schema v2 non
    li prevede, e scriverli per poi rimuoverli sarebbe rumore.
    """
    used_uids = _folded(taken_uids)
    candidate = ""
    if identify:
        if uid is not None:
            requested = str(uid).strip()
            if not requested:
                raise ValueError("uid vuoto: indicare un valore non vuoto.")
            if requested.casefold() in used_uids:
                raise ValueError(
                    f"uid '{requested}' già usato da una dashboard esistente."
                )
            candidate = requested
        else:
            candidate = new_uid_not_in(used_uids)

    final_title = unique_title(title or db.get("title") or "Dashboard", taken_titles)

    if identify:
        db["uid"] = candidate
        db["id"] = None
        db["version"] = 1
    db["title"] = final_title
    return DashboardIdentity(uid=candidate, title=final_title)


def renumber_dashboard(db: dict[str, Any]) -> int:
    """Rinumera gli id da 1, nell'ordine in cui compaiono nel file.

    Serve a un fork: una dashboard nuova non deve portarsi dietro la
    numerazione della precedente. Ritorna quanti oggetti hanno un id.
    """
    next_id = 1
    for root in dashboard_roots(db):
        next_id = renumber_ids(root, next_id)
    return next_id - 1


def detach_bindings(
    db: dict[str, Any],
    *,
    keep_library: bool = False,
    keep_alerts: bool = False,
    strip_links: bool = False,
) -> dict[str, int]:
    """Stacca i vincoli che legano la copia alla dashboard originale.

    - `libraryPanel`: il pannello copiato torna inline, senza dipendere da una
      libreria che l'utente non controlla;
    - `alert` / `alertId`: le regole di alert non si copiano, perché
      continuerebbero a notificare per una dashboard che non è più quella;
    - `links`: rimossi solo su richiesta, perché normalmente fanno parte del
      contenuto.

    Ritorna il conteggio delle rimozioni per tipo.
    """
    counts = {"library": 0, "alerts": 0, "links": 0}
    for panel in iter_all_panels(db):
        if not keep_library and "libraryPanel" in panel:
            panel.pop("libraryPanel")
            counts["library"] += 1
        if not keep_alerts and ("alert" in panel or "alertId" in panel):
            panel.pop("alert", None)
            panel.pop("alertId", None)
            counts["alerts"] += 1

    if strip_links:
        links = db.get("links")
        if isinstance(links, list):
            counts["links"] = len(links)
            db["links"] = []
    return counts


def id_range_collisions(db: dict[str, Any], base: int, count: int) -> list[int]:
    """Id già presenti nella dashboard che cadrebbero nell'intervallo richiesto."""
    used = {
        p.get("id")
        for p in iter_all_panels(db)
        if isinstance(p.get("id"), int)
    }
    return sorted(i for i in range(base, base + count) if i in used)
