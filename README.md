# grafana-tool

CLI per leggere, validare e modificare dashboard Grafana esportate in JSON. Nessuna dipendenza di runtime: solo standard library Python 3.9+.

Ogni comando legge il file indicato, lavora in memoria e scrive un file di output separato. Il file di input non viene mai modificato.

## A cosa serve

Serve quando una dashboard Grafana va gestita come file, fuori dall'interfaccia web:

- ispezionare righe e pannelli di una dashboard esportata;
- creare, rinominare, spostare, copiare ed eliminare righe e pannelli;
- estrarre una singola vista in una dashboard autonoma;
- aggiornare in blocco query e datasource;
- rifare il layout dei pannelli;
- validare la struttura prima di importare il file in Grafana.

Per iniziare, esporta la dashboard da Grafana con **Dashboard settings > JSON Model** e salvala come `dashboard.json`. Nel repository trovi `examples/full_dashbaord.json`, una dashboard reale usata negli esempi.

## Indice

1. [A cosa serve](#a-cosa-serve)
2. [Installazione e avvio](#installazione-e-avvio)
3. [Come è fatta una dashboard](#come-è-fatta-una-dashboard)
4. [Come sono fatti i comandi](#come-sono-fatti-i-comandi)
5. [Selettori: quali oggetti](#selettori-quali-oggetti)
6. [Opzioni comuni dei comandi di scrittura](#opzioni-comuni-dei-comandi-di-scrittura)
7. [Contratto I/O](#contratto-io)
8. [Exit code](#exit-code)
9. [`list`: leggere](#list-leggere)
10. [`create`: creare](#create-creare)
11. [`update`: aggiornare](#update-aggiornare)
12. [`delete`: eliminare](#delete-eliminare)
13. [`move`: spostare](#move-spostare)
14. [`extract`: estrarre](#extract-estrarre)
15. [`layout`, `validate`, `lint`: dashboard](#layout-validate-lint-dashboard)
16. [Simmetria fra righe e pannelli](#simmetria-fra-righe-e-pannelli)
17. [Dashboard nuove e nomi](#dashboard-nuove-e-nomi)
18. [Pipeline di esempio](#pipeline-di-esempio)
19. [Errori e log](#errori-e-log)
20. [Sviluppo](#sviluppo)

## Installazione e avvio

Requisiti: Python 3.9 o superiore, nessuna dipendenza esterna.

```bash
# installazione normale
python3 -m pip install .

# installazione in modalità sviluppo, dalla cartella del progetto
python3 -m pip install -e .

grafana-utils --version         # grafana-utils 5.0.0
python3 -m grafana_tool --help  # stesso comando senza installare lo script
```

Negli esempi si usa `grafana-utils`. Se il pacchetto non è installato, la stessa invocazione funziona con `python3 -m grafana_tool`. Gli esempi partono da `examples/full_dashbaord.json`; sostituisci il percorso con il tuo file.

Il parser richiede sempre un sottocomando: `grafana-utils` da solo produce un errore d'uso con exit code 2.

## Come è fatta una dashboard

Una dashboard esportata da Grafana è un oggetto JSON con righe e pannelli. Il file può rappresentare le righe in tre modi, tutti supportati dal tool:

- schema moderno: `panels` mescola pannelli di contenuto e contenitori `type: "row"`, i cui figli stanno in `row.panels`;
- schema legacy: la lista `rows` contiene direttamente le righe;
- riga espansa: se `row.collapsed` è `false`, Grafana non mette i figli in `row.panels`; i pannelli restano top-level subito dopo la riga, fino alla riga successiva.

Non serve conoscere la differenza per usare i comandi: il tool risolve i pannelli di ogni riga nello stesso modo, righe espanse comprese.

## Come sono fatti i comandi

Tutti i comandi hanno la stessa forma:

```text
grafana-utils <verbo> <tipo> <file> [selettori] [impostazioni]
```

- **verbo**: `list`, `create`, `update`, `delete`, `move`, `extract`, più `layout`, `validate` e `lint` che non lavorano su un singolo oggetto.
- **tipo**: `row` oppure `panel`. È sempre lo stesso nome, per tutti i verbi.
- **file**: la dashboard da leggere, che non viene mai modificata.

I verbi CRUD non hanno una versione "per riga" e una "per pannello": `delete row` e `delete panel` sono lo stesso comando, con lo stesso set di opzioni. Se un'operazione non ha senso per il tipo scelto, il comando lo dice invece di ignorarla.

```bash
grafana-utils list   row   dashboard.json
grafana-utils update panel dashboard.json --id 12 --title "Latenza p99"
grafana-utils delete row   dashboard.json --match-title "^DEBUG"
grafana-utils move   panel dashboard.json --id 12 --to-row 5
```

## Selettori: quali oggetti

I selettori sono identici per ogni verbo e per ogni tipo. Scelgono *quali* oggetti toccare; tutte le altre opzioni *impostano* un valore.

| Selettore | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `--id N` | intero, ripetibile | nessuno | opzionale; indipendente | Seleziona l'oggetto con quell'id. Ripetibile per più oggetti |
| `--match-title REGEX` | regex | nessuno | opzionale; indipendente | Seleziona gli oggetti il cui titolo matcha; mai case-sensitive |
| `--match-type TIPO` | stringa | nessuno | solo `panel`; indipendente | Seleziona i pannelli di quel tipo (`timeseries`, `text`, ...) |
| `--in-row N` | intero | nessuno | solo `panel`; indipendente | Limita ai pannelli della riga `N` |

Regola mnemonica: **`--match-*` seleziona, le altre opzioni impostano**. `--title` è il nuovo titolo, `--match-title` è il filtro.

I selettori si combinano in AND:

```bash
# i pannelli timeseries della riga 125 il cui titolo inizia per POD
grafana-utils update panel dashboard.json --in-row 125 --match-type timeseries --match-title "^POD" --title "POD"
```

Se un `--id` non esiste, il comando fallisce con exit code 1 e un messaggio che elenca gli id mancanti. Se l'id appartiene a una riga e hai chiesto `panel`, il messaggio suggerisce il tipo giusto.

`delete`, `move` ed `extract` pretendono almeno un selettore: non esiste un "tutti" implicito per le operazioni distruttive. `list` e `update` senza selettori lavorano su tutti gli oggetti del tipo.

## Opzioni comuni dei comandi di scrittura

Tutti i comandi che scrivono un file (`create`, `update`, `delete`, `move`, `extract`, `layout`) accettano:

| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `-o FILE`, `--output FILE` | path | `<input>_out.json` | opzionale; indipendente | File JSON di output; l'input non viene mai sovrascritto |
| `--dry-run` | flag | off | opzionale; indipendente | Non scrive nulla, ma esegue comunque la validazione in memoria |
| `--severity {info,warning,error}` | scelta | `error` | opzionale; indipendente | Soglia che fa fallire la validazione finale |

I comandi che creano o rinominano oggetti (`create`, `update`, `extract`) accettano anche `--dedupe-titles`, che rende unico il titolo rispetto agli altri già presenti nella dashboard, aggiungendo ` (2)`, ` (3)`.

## Contratto I/O

| Situazione | File prodotto |
| --- | --- |
| Scrittura riuscita, `-o` omesso | `<input>_out.json` nella stessa directory |
| Scrittura riuscita, `-o FILE` | `FILE` |
| Validazione fallita, `-o` omesso | `<input>_out_ERROR_<TIPO>.json` |
| Validazione fallita, `-o FILE` | `<stem di FILE>_ERROR_<TIPO>.json` |
| `--dry-run` | nessun file; il report di validazione viene comunque stampato |

I due soli `<TIPO>` usati nel nome sono `VALIDATION_ERROR` (ID duplicati o mancanti) e `LINT_ERROR` (issue oltre la soglia).

```text
dashboard.json                      -> dashboard_out.json
dashboard.json + errore di lint     -> dashboard_out_ERROR_LINT_ERROR.json
build/new.json + errore strutturale -> build/new_ERROR_VALIDATION_ERROR.json
```

## Exit code

| Codice | Significato |
| --- | --- |
| 0 | Successo |
| 1 | Errore di comando, validazione fallita o issue di lint oltre soglia |
| 2 | Errore di input o d'uso (file assente, JSON non valido, argomenti mancanti) |
| 3 | Errore di output (path non scrivibile, directory al posto del file) |

## `list`: leggere

Elenca gli oggetti del tipo indicato, senza scrivere nulla.

| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `--format {text,json}` | scelta | `text` | opzionale; indipendente | `json` produce un array di oggetti, utile in pipeline |
| selettori | - | nessuno | opzionale; nessun selettore = tutti | Vedi [Selettori](#selettori-quali-oggetti) |

Le righe riportano id, titolo, numero di pannelli e stato `collapsed` (il conteggio include i pannelli delle righe espanse). I pannelli riportano id, tipo, titolo, riga di appartenenza e un'anteprima della query.

```bash
grafana-utils list row dashboard.json
grafana-utils list panel dashboard.json --in-row 125 --match-type timeseries
grafana-utils list panel dashboard.json --format json | jq '.[].id'
```

## `create`: creare

Crea una riga o un pannello a partire da un oggetto esistente oppure da un template.

| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `--from-id N` | intero | nessuno | alternativa a `--template` | Copia l'oggetto con quell'id, figli compresi |
| `--template FILE` | path | `templates/system-view.row.tpl.json` per `row`; obbligatorio per `panel` | alternativa a `--from-id` | Istanzia il template JSON |
| `--title T` | stringa | titolo della sorgente | opzionale; indipendente | Titolo del nuovo oggetto; non può essere vuoto |
| `--dedupe-titles` | flag | off | opzionale; indipendente | Rende unici titolo e titoli dei figli |
| `--collapsed` / `--expanded` | flag | `collapsed` | solo `row` | Stato della nuova riga |
| `--to-row N` | intero | stessa riga della sorgente | solo `panel`; indipendente | Riga di destinazione del pannello |
| `--position {top,bottom}` | scelta | `bottom` | opzionale; indipendente | In cima o in fondo alla dashboard (righe) o alla riga (pannelli) |
| `--replace OLD=NEW` | ripetibile | nessuno | opzionale; indipendente | Sostituzione su `target[*].expr` dei nuovi pannelli |
| `--base-id N` | intero | `max id + 1` | opzionale; indipendente | Primo id dei nuovi oggetti; in conflitto è un errore |
| `--params FILE` | path | nessuno | con `--template`; indipendente | Parametri JSON/YAML per i segnaposto `${...}` |
| `--namespace V`, `--cluster-gen V`, `--datasource-uid V`, `--title-prefix V` | stringa | vedi sotto | con `--template` di riga | Scorciatoie per `${NAMESPACE}`, `${CLUSTER_GEN}`, `${DATASOURCE_UID}`, `${TITLE_PREFIX}` |
| `--namespace-exact` | flag | off | con `--template`; indipendente | Non riscrive `namespace="x"` in `namespace=~"x"` |
| `--on-existing {error,replace,skip,append}` | scelta | `error` | solo `row` con `--template` | Cosa fare se esiste già una riga con lo stesso titolo |

Con `--from-id`, la copia è fedele: stesso titolo della sorgente, salvo `--title`; usa `--dedupe-titles` per evitare ambiguità. Con `--template`, i segnaposto `${...}` vengono sostituiti dai valori di `--params` e delle scorciatoie, e i default sono `universo-on-line-feu-up`, `2`, `QEIISg1Vz`, stringa vuota.

```bash
# copia di una riga, con nomi unici
grafana-utils create row dashboard.json --from-id 125 --dedupe-titles

# riga di sistema dal template, con namespace e cluster espliciti
grafana-utils create row dashboard.json --namespace pa-digital --cluster-gen 3 --title "VISTA TEST"

# copia di un pannello accanto all'originale
grafana-utils create panel dashboard.json --from-id 12

# pannello in un'altra riga, con query riscritta
grafana-utils create panel dashboard.json --from-id 12 --to-row 125 --replace "gen2=gen3"
```

`--on-existing` vale solo per i template di riga: `error` (default) blocca, `replace` elimina la riga esistente prima di creare, `skip` lascia la dashboard com'è, `append` crea comunque un duplicato.

## `update`: aggiornare

Applica una o più modifiche agli oggetti selezionati. Almeno una impostazione è obbligatoria.

| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `--title T` | stringa | nessuno | almeno un'impostazione | Nuovo titolo; non può essere vuoto |
| `--dedupe-titles` | flag | off | con `--title` | Rende unico il nuovo titolo |
| `--collapsed` / `--expanded` | flag | nessuno | solo `row` | Cambia lo stato della riga spostando i figli nella rappresentazione giusta |
| `--replace OLD=NEW` | ripetibile | nessuno | almeno un'impostazione | Sostituzione su `target[*].expr` |
| `--datasource UID` | stringa | nessuno | almeno un'impostazione | Imposta `datasource.uid` di pannelli e target |
| `--datasource-type TIPO` | stringa | nessuno | richiede `--datasource` | Imposta anche `datasource.type` |
| `--datasource-create` | flag | off | richiede `--datasource` | Crea il blocco datasource se assente |
| selettori | - | tutti | opzionale | Vedi [Selettori](#selettori-quali-oggetti) |

Su una **riga**, `--replace` e `--datasource` si applicano a tutti i pannelli che le appartengono: la stessa operazione che faresti su un pannello, estesa al suo contenuto. Su un pannello si applicano al pannello e ai suoi eventuali annidati.

```bash
# rinomina (una riga)
grafana-utils update row dashboard.json --id 125 --title "VISTA SISTEMISTICA"

# espande la riga: i figli passano top-level subito dopo
grafana-utils update row dashboard.json --id 125 --expanded

# cambia datasource a tutti i pannelli di una riga
grafana-utils update row dashboard.json --id 125 --datasource prom-new --datasource-type prometheus

# riscrive le query dei soli pannelli timeseries che iniziano per POD
grafana-utils update panel dashboard.json --match-type timeseries --match-title "^POD" --replace "gen2=gen3"
```

## `delete`: eliminare

| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `--keep-children` | flag | off | solo `row`; indipendente | Promuove i pannelli della riga a top-level invece di eliminarli |
| selettori | - | nessuno | **obbligatorio** | Vedi [Selettori](#selettori-quali-oggetti) |

Eliminare una riga elimina anche i pannelli che le appartengono, righe espanse comprese. `--keep-children` conserva i pannelli e rimuove solo l'intestazione.

```bash
grafana-utils delete panel dashboard.json --id 12
grafana-utils delete panel dashboard.json --match-title "^DEBUG" --dry-run
grafana-utils delete row   dashboard.json --match-title "^VISTA" --keep-children
```

## `move`: spostare

| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `--to-row N` | intero | nessuno | solo `panel`; alternativo a `--before`/`--after` | Riga di destinazione del pannello |
| `--before N` | intero | nessuno | alternativo a `--to-row` e `--after` | Posiziona prima dell'oggetto con questo id |
| `--after N` | intero | nessuno | alternativo a `--to-row` e `--before` | Posiziona dopo l'oggetto con questo id |
| `--position {top,bottom}` | scelta | `bottom` | con `--to-row` o da solo | In cima o in fondo al contenitore |
| selettori | - | nessuno | **obbligatorio** | Vedi [Selettori](#selettori-quali-oggetti) |

Le righe si riordinano tra loro (`--position`, `--before`, `--after`), i pannelli si spostano in un'altra riga (`--to-row`) o si riordinano dentro la propria (`--before`, `--after`).

```bash
# sposta un pannello nella riga 125, in coda
grafana-utils move panel dashboard.json --id 12 --to-row 125

# sposta tutti i pannelli della riga 5 nella riga 125
grafana-utils move panel dashboard.json --in-row 5 --to-row 125

# porta la riga 125 in cima alla dashboard
grafana-utils move row dashboard.json --id 125 --position top

# mette la riga 125 subito dopo la riga 112
grafana-utils move row dashboard.json --id 125 --after 112
```

## `extract`: estrarre

Produce una dashboard minima con il solo oggetto selezionato: uid nuovo, `id` nullo, `version` 1, id dei pannelli rinumerati a partire da `max id + 1` della sorgente, `gridPos` riportata a `y = 0`.

| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `--title T` | stringa | titolo dell'oggetto | opzionale; indipendente | Titolo della dashboard di output |
| `--uid U` | stringa | generato | opzionale; indipendente | uid della dashboard; in conflitto con l'inventario è un errore |
| `--existing-dashboards FILE` | path | nessuno | opzionale; indipendente | Inventario JSON delle dashboard già presenti in Grafana |
| `--base-id N` | intero | `max id + 1` | opzionale; indipendente | Primo id dei pannelli estratti |
| `--dedupe-titles` | flag | off | opzionale; indipendente | Rende unici i titoli dei pannelli estratti |
| selettori | - | nessuno | **obbligatorio**, **un solo oggetto** | Vedi [Selettori](#selettori-quali-oggetti) |

Una riga espansa viene estratta nella sua forma originale: riga più pannelli top-level subito dopo. Una riga collassata conserva i figli annidati. Un pannello produce una dashboard con un solo pannello.

L'inventario accetta la risposta di `GET /api/search` (lista di `{uid, title}`), un oggetto `{"dashboards": [...]}` o una singola dashboard.

```bash
grafana-utils extract row   dashboard.json --id 125 -o vista.json
grafana-utils extract panel dashboard.json --id 12  -o pannello.json
grafana-utils extract row   dashboard.json --match-title "Sistemistica" --existing-dashboards inv.json
```

## `layout`, `validate`, `lint`: dashboard

Questi tre comandi non scelgono un tipo: lavorano sulla dashboard intera.

`layout` ricalcola i `gridPos` dei pannelli riga per riga.

| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `--in-row N` | intero | tutte le righe | opzionale; indipendente | Limita il ricalcolo a una riga |
| `--columns N` | intero | `24` | opzionale; indipendente | Larghezza della griglia; deve essere > 0 |
| `--default-width N` | intero | `12` | opzionale; indipendente | Larghezza usata quando il pannello non ne ha una |
| `--default-height N` | intero | `8` | opzionale; indipendente | Altezza usata quando il pannello non ne ha una |

```bash
grafana-utils layout dashboard.json --in-row 125
grafana-utils layout dashboard.json --columns 12 -o stretto.json
```

`validate` esegue struttura e lint, `lint` solo il lint. `validate` accetta `--severity`; `lint` accetta `--format text|json` e `--severity`.

```bash
grafana-utils validate vista.json
grafana-utils lint dashboard.json --format json --severity warning
```

## Simmetria fra righe e pannelli

| Operazione | `row` | `panel` | Note |
| --- | --- | --- | --- |
| `list` | sì | sì | |
| `create --from-id` | sì | sì | |
| `create --template` | sì | sì | per le righe esiste un template predefinito |
| `update --title` | sì | sì | |
| `update --replace` | sì | sì | su una riga vale per tutti i suoi pannelli |
| `update --datasource` | sì | sì | su una riga vale per tutti i suoi pannelli |
| `update --collapsed/--expanded` | sì | no | un pannello non è un contenitore: il comando lo rifiuta |
| `delete` | sì | sì | |
| `delete --keep-children` | sì | no | un pannello non ha figli propri |
| `move --position/--before/--after` | sì | sì | |
| `move --to-row` | no | sì | le righe non si annidano |
| `extract` | sì | sì | |

Le due sole asimmetrie sono strutturali: una riga è un contenitore (quindi ha `collapsed` e dei figli da conservare), un pannello no. In entrambi i casi il comando rifiuta l'opzione con un messaggio esplicito, invece di ignorarla.

## Dashboard nuove e nomi

Tre livelli di identità, con regole diverse:

- **dashboard**: `uid` globale, generato di 9 caratteri alfanumerici e verificato contro l'inventario; `id` posto a `null`; `version` a `1`. Così Grafana crea una dashboard nuova e non aggiorna quella esistente.
- **pannello**: l'`id` è un intero unico *dentro* la dashboard. I comandi che creano pannelli partono da `max + 1` o da `--base-id` e verificano che l'intervallo sia libero: un `--base-id` in conflitto è un errore, non una rinumerazione silenziosa.
- **titolo**: è un'etichetta, non una chiave. I titoli restano invariati per default; con `--dedupe-titles` diventano unici nella dashboard, con il suffisso ` (2)`, ` (3)`.

Il confronto per nome è sempre case-insensitive: `--match-title` non distingue maiuscole e minuscole.

## Pipeline di esempio

```bash
# 1. ispeziona
grafana-utils list row examples/full_dashbaord.json

# 2. estrai la vista sistemistica in una dashboard autonoma
grafana-utils extract row examples/full_dashbaord.json \
  --match-title "Sistemistica" -o build/sistemistica.json

# 3. rinomina la riga e rendi unico il titolo
#    (extract rinumera gli id: qui si seleziona per titolo)
grafana-utils update row build/sistemistica.json --match-title "Sistemistica" \
  --title "VISTA SISTEMISTICA" --dedupe-titles -o build/passo1.json

# 4. togli i pannelli di debug e cambia datasource
grafana-utils delete panel build/passo1.json --match-title "^DEBUG" -o build/passo2.json
grafana-utils update row build/passo2.json --match-title "^VISTA SISTEMISTICA" \
  --datasource prom-prod -o build/passo3.json

# 5. rifai il layout e valida
grafana-utils layout build/passo3.json -o build/finale.json
grafana-utils validate build/finale.json
```

Ogni passo scrive un file nuovo: se qualcosa non torna, il passo precedente è ancora lì. Con `--dry-run` vedi il report di validazione senza produrre file.

## Errori e log

Ogni errore viene classificato e registrato in `out/` con un nome `<tipo>_error_<AAAAMMGG-HHMMSS>.txt`. La directory si sposta con la variabile `GRAFANA_TOOL_LOG_DIR`. Un log mancante non maschera mai l'errore originale.

| Tipo | Quando | Exit |
| --- | --- | --- |
| `INPUT_ERROR` | file assente, non leggibile, JSON non valido, radice non oggetto | 2 |
| `USAGE_ERROR` | comando o argomenti non validi | 2 |
| `OUTPUT_ERROR` | path di output non scrivibile | 3 |
| `COMMAND_ERROR` | selettore mancante, oggetto inesistente, opzione incoerente | 1 |
| `VALIDATION_ERROR` | ID duplicati o mancanti | 1 |
| `LINT_ERROR` | issue con severità pari o superiore alla soglia | 1 |

## Sviluppo

La suite usa solo `unittest`:

```bash
python3 -m unittest discover -s tests -t . -v
```

Ogni sottocomando è una classe in `grafana_tool/commands/` che eredita `ReadCommand` o `WriteCommand` da `grafana_tool/command_base.py`: la classe base fa caricamento, copia difensiva, salvataggio e validazione, il comando implementa solo la propria logica. Il livello che rende righe e pannelli intercambiabili sta in `grafana_tool/objects.py`, i selettori in `grafana_tool/model.py`, le opzioni condivise in `grafana_tool/cli_common.py`.

Per architettura dei moduli, pipeline interna, regole del linter e dettagli implementativi la documentazione di riferimento è [AGENTS.md](AGENTS.md).
