# grafana-tool

CLI modulare per leggere, validare e modificare dashboard Grafana esportate in JSON. Nessuna dipendenza di runtime: solo standard library Python 3.9+.

Ogni comando legge il file indicato, lavora in memoria e scrive un file di output separato. Il file di input non viene mai modificato.

## A cosa serve

Serve quando una dashboard Grafana va gestita come file, fuori dall'interfaccia web:

- ispezionare righe e pannelli di una dashboard esportata;
- clonare una riga o un pannello per un nuovo servizio;
- estrarre una singola vista in una dashboard autonoma;
- aggiornare in blocco query e datasource;
- ripulire pannelli inutili e rifare il layout;
- validare la struttura prima di importare il file in Grafana.

Per iniziare, esporta la dashboard da Grafana con **Dashboard settings > JSON Model** e salvala come `dashboard.json`. Nel repository trovi `examples/full_dashbaord.json`, una dashboard reale usata negli esempi.

## Indice

1. [A cosa serve](#a-cosa-serve)
2. [Installazione e avvio](#installazione-e-avvio)
3. [Come è fatta una dashboard](#come-è-fatta-una-dashboard)
4. [Contratto I/O](#contratto-io)
5. [Exit code](#exit-code)
6. [Opzioni comuni dei comandi di scrittura](#opzioni-comuni-dei-comandi-di-scrittura)
7. [Dashboard nuove e nomi](#dashboard-nuove-e-nomi)
8. [Comandi read-only](#comandi-read-only)
9. [Comandi di scrittura](#comandi-di-scrittura)
10. [Pipeline di esempio](#pipeline-di-esempio)
11. [Errori e log](#errori-e-log)
12. [Sviluppo](#sviluppo)

## Installazione e avvio

Requisiti: Python 3.9 o superiore, nessuna dipendenza esterna.

```bash
# installazione normale
python3 -m pip install .

# installazione in modalità sviluppo, dalla cartella del progetto
python3 -m pip install -e .

grafana-utils --version         # grafana-utils 3.1.0
python3 -m grafana_tool --help  # stesso comando senza installare lo script
```

Negli esempi si usa `grafana-utils`. Se il pacchetto non è installato, la stessa invocazione funziona con `python3 -m grafana_tool`.

Gli esempi partono da `examples/full_dashbaord.json`; sostituisci il percorso con il tuo file.

Il parser richiede sempre un sottocomando: `grafana-utils` da solo produce un errore d'uso con exit code 2.

## Come è fatta una dashboard

Una dashboard esportata da Grafana è un oggetto JSON con righe e pannelli. Il file può rappresentare le righe in tre modi, tutti supportati dal tool:

- schema moderno: `panels` mescola pannelli di contenuto e contenitori `type: "row"`, i cui figli stanno in `row.panels`;
- schema legacy: la lista `rows` contiene direttamente le righe;
- riga espansa: se `row.collapsed` è `false`, Grafana non mette i figli in `row.panels`; i pannelli restano top-level subito dopo la riga, fino alla riga successiva.

Non serve conoscere la differenza per usare i comandi: il tool risolve i pannelli di ogni riga nello stesso modo e gestisce anche le righe espanse.

## Contratto I/O


| Situazione                       | File prodotto                                                 |
| ---------------------------------- | --------------------------------------------------------------- |
| Scrittura riuscita, `-o` omesso  | `<input>_out.json` nella stessa directory                     |
| Scrittura riuscita, `-o FILE`    | `FILE`                                                        |
| Validazione fallita, `-o` omesso | `<input>_out_ERROR_<TIPO>.json`                               |
| Validazione fallita, `-o FILE`   | `<stem di FILE>_ERROR_<TIPO>.json`                            |
| `--dry-run`                      | nessun file; il report di validazione viene comunque stampato |

I due soli `<TIPO>` usati nel nome sono `VALIDATION_ERROR` (ID duplicati o mancanti) e `LINT_ERROR` (issue oltre la soglia).

```text
dashboard.json                      -> dashboard_out.json
dashboard.json + errore di lint     -> dashboard_out_ERROR_LINT_ERROR.json
build/new.json + errore strutturale -> build/new_ERROR_VALIDATION_ERROR.json
```

## Exit code


| Codice | Significato                                                                 |
| -------- | ----------------------------------------------------------------------------- |
| 0      | Successo                                                                    |
| 1      | Errore di comando, validazione fallita o issue di lint oltre soglia         |
| 2      | Errore di input o d'uso (file assente, JSON non valido, argomenti mancanti) |
| 3      | Errore di output (path non scrivibile, directory al posto del file)         |

## Opzioni comuni dei comandi di scrittura

Tutti i comandi di scrittura accettano:


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `-o FILE`, `--output FILE` | path | `<input>_out.json` | opzionale; indipendente | File JSON di output; l'input non viene mai sovrascritto |
| `--dry-run` | flag | off | opzionale; indipendente | Non scrive nulla, ma esegue comunque la validazione in memoria |
| `--lint-severity {info,warning,error}` | scelta | `error` | opzionale; indipendente | Soglia che fa fallire la validazione finale |

I comandi che creano righe o pannelli (`duplicate-row`, `copy-panel`, `append-row`, `extract-row`) accettano anche:


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `--dedupe-titles` | flag | off | opzionale; solo per i comandi che creano righe o pannelli | Rende unici i titoli creati: se il nome esiste già aggiunge ` (2)`, ` (3)` |

L'identificazione per nome è sempre case-insensitive: `--row-match`, `--match-title` e `--match-type` non distinguono maiuscole e minuscole.

Legenda delle tabelle: "obbligatorio" significa che senza l'opzione il comando non parte; "opzionale" che esiste un default. La colonna "Obbligo / dipendenze" indica anche quando un'opzione ha effetto solo insieme a un'altra.

## Dashboard nuove e nomi

Quando importi in Grafana un file prodotto dal tool, il comportamento dipende dal comando che lo ha generato:

| Comando | Cosa succede in Grafana |
| --- | --- |
| `extract-row` | crea una dashboard nuova; non sovrascrive quella di partenza |
| `duplicate-row`, `copy-panel`, `append-row` | aggiornano la dashboard di partenza, aggiungendo righe o pannelli |
| `replace`, `transform`, `prune`, `reflow`, `set-datasource`, `move-panel` | aggiornano la dashboard di partenza, senza cambiarne l'identità |

`extract-row` assegna alla dashboard un uid nuovo, azzera l'id e riparte con la numerazione dei pannelli dopo l'ultimo id della sorgente: il file non riusa l'identità di oggetti già presenti. Se conosci le dashboard già caricate in Grafana, passa `--existing-dashboards` (vedi [extract-row](#extract-row)) per evitare anche collisioni di nome.

I nomi degli oggetti creati restano quelli della sorgente. Con `--dedupe-titles` diventano unici nella dashboard: se il nome esiste già ricevono il suffisso ` (2)`, ` (3)`.

## Comandi read-only

Non producono file di dashboard.

### list-rows

Elenca le righe con ID, titolo, numero di pannelli e stato `collapsed`.

```bash
grafana-utils list-rows FILE
```


| Opzione | Obbligo / dipendenze | Descrizione |
| --- | --- | --- |
| `FILE` | obbligatorio; nessuna dipendenza | Dashboard JSON |

Nessuna opzione oltre a `FILE`: il comando è di sola lettura.

```bash
grafana-utils list-rows examples/full_dashbaord.json
```

```text
    ID  Titolo                                              Pannelli  Collapsed
----------------------------------------------------------------------------------
   197  ALERT                                                      3       True
   199  Volumi di Business                                        13       True
```

### list-panels

Elenca i pannelli di contenuto indicando la riga di appartenenza e, quando presente, la prima query `expr`.

```bash
grafana-utils list-panels FILE [--row ID]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--row ID` | int | nessuno | opzionale; se presente la riga deve esistere; indipendente | Limita ai pannelli di quella riga |

```bash
grafana-utils list-panels examples/full_dashbaord.json
grafana-utils list-panels examples/full_dashbaord.json --row 197
```

```text
- [200] text: (senza titolo)  (riga 197)
- [194] alertlist: Alert ATTIVI KO  (riga 197)
- [161] timeseries: Emissioni Polizza (Fonte PV-OCP)  (riga 199)
    expr: sum by (app,action)(increase(http_request_duration_seconds_count{...
```

### validate

Esegue i controlli strutturali e il linter. È lo stesso controllo che chiude ogni scrittura.

```bash
grafana-utils validate FILE [--severity {info,warning,error}]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--severity` | `info`, `warning`, `error` | `error` | opzionale; indipendente; abbassa la soglia di fallimento, non cambia le issue mostrate | Soglia che fa fallire il comando |

```bash
grafana-utils validate examples/full_dashbaord.json
grafana-utils validate examples/full_dashbaord.json --severity warning
```

```text
Dashboard: righe: 6, pannelli: 90
Validazione: nessun errore strutturale.
Lint: 55 issue (0 error, 25 warning, 30 info) - soglia: error
  WARN [MISSING_TITLE] Pannello 200 senza titolo.
  INFO [MISSING_UNIT] Pannello 35 senza unità di misura.
```

Esce con 1 se ci sono errori strutturali o issue oltre la soglia, registrando il relativo log in `out/`.

### lint

Esegue solo le regole di best practice, senza controlli strutturali.

```bash
grafana-utils lint FILE [--format {text,json}] [--severity {info,warning,error}]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--format` | `text`, `json` | `text` | opzionale; indipendente; con `json` non stampa il totale e manda il log su stderr | Formato dell'output |
| `--severity` | `info`, `warning`, `error` | `error` | opzionale; indipendente; governa solo exit code e log, non filtra le issue mostrate | Exit 1 se esiste almeno una issue pari o superiore alla soglia |

```bash
grafana-utils lint examples/full_dashbaord.json
grafana-utils lint examples/full_dashbaord.json --format json
grafana-utils lint examples/full_dashbaord.json --severity warning
```

Regole predefinite:


| Codice                 | Severità | Scatta quando                                               |
| ------------------------ | ----------- | ------------------------------------------------------------- |
| `MISSING_PANEL_ID`     | error     | Un pannello o una riga non ha `id`                          |
| `DUPLICATE_PANEL_ID`   | error     | Lo stesso `id` intero compare più volte                    |
| `MISSING_TITLE`        | warning   | Un pannello di contenuto non ha titolo                      |
| `MISSING_TARGETS`      | warning   | Un pannello dati non ha `targets`                           |
| `DUPLICATE_QUERY`      | warning   | La stessa `expr` compare in pannelli diversi                |
| `MISSING_DATASOURCE`   | warning   | Un pannello con target non dichiara datasource              |
| `EMPTY_ROW`            | warning   | Una riga vuota e non `collapsed`                            |
| `MISSING_UNIT`         | info      | Un pannello numerico senza unità di misura                 |
| `SHARED_LIBRARY_PANEL` | info      | Un pannello usa una libreria condivisa (`libraryPanel.uid`) |

## Comandi di scrittura

Tutti accettano le [opzioni comuni](#opzioni-comuni-dei-comandi-di-scrittura), non modificano mai l'input e terminano con la validazione finale.

### duplicate-row

Crea una nuova riga copiando i pannelli di un'altra e la inserisce subito dopo il blocco della sorgente. La riga originale non viene modificata.

```bash
grafana-utils duplicate-row FILE --source ID [opzioni]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--source ID` | int | obbligatorio | obbligatorio; la riga deve esistere | ID della riga da copiare |
| `--new-title TESTO` | stringa | `<titolo>_COPY` | opzionale; indipendente; con `--dedupe-titles` può ricevere un suffisso | Titolo della nuova riga |
| `--replace OLD=NEW` | ripetibile | vuoto | opzionale; indipendente | Sostituzioni su `target[*].expr` dei cloni |
| `--dedupe-titles` | flag | off | opzionale; indipendente; agisce sul titolo della riga e sui pannelli copiati | Rende unici titoli di riga e pannelli copiati |

```bash
# titolo automatico: <titolo>_COPY
grafana-utils duplicate-row dashboard.json --source 69 -o copia.json
# Nuova riga 120 "PA-DIGITAL FrontEnd Checkup-app_COPY" creata dopo la riga 69, con 23 pannelli.

# titolo e query personalizzati
grafana-utils duplicate-row dashboard.json --source 69 \
    --new-title "PA-DIGITAL FrontEnd Checkup-bff" \
    --replace checkup-app=checkup-bff -o copia.json
```

La copia è sempre `collapsed: true`, con i pannelli dentro `row.panels`, perché una riga espansa ignorerebbe i figli annidati.

### copy-panel

Duplica un singolo pannello assegnandogli un nuovo `id`.

```bash
grafana-utils copy-panel FILE --panel-id ID [opzioni]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--panel-id ID` | int | obbligatorio | obbligatorio; deve puntare a un pannello, non a una riga | Pannello da copiare |
| `--target-row ID` | int | stessa riga | opzionale; se presente deve esistere e non contenere già il pannello; senza, il clone resta dopo l'originale | Riga di destinazione |
| `--new-title TESTO` | stringa | invariato | opzionale; indipendente; con `--dedupe-titles` può ricevere un suffisso | Titolo del clone |
| `--replace OLD=NEW` | ripetibile | vuoto | opzionale; indipendente | Sostituzioni su `target[*].expr` del clone |
| `--dedupe-titles` | flag | off | opzionale; indipendente; può modificare il titolo del clone | Rende unico il titolo del clone |

```bash
# il clone resta nella stessa riga, subito dopo l'originale
grafana-utils copy-panel dashboard.json --panel-id 82 -o copia.json
# Pannello 82 copiato come id 120.

# il clone va nella riga 72, con titolo e query nuovi
grafana-utils copy-panel dashboard.json --panel-id 82 --target-row 72 \
    --new-title "Disp. % FrontEnd Checkup-bff" \
    --replace checkup-app=checkup-bff -o copia.json
```

Le righe non sono clonabili: `--panel-id` deve puntare a un pannello di contenuto.

### move-panel

Sposta un pannello in un'altra riga senza cambiarne l'`id`.

```bash
grafana-utils move-panel FILE --panel-id ID --target-row ID [opzioni]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--panel-id ID` | int | obbligatorio | obbligatorio; deve puntare a un pannello, non a una riga | Pannello da spostare |
| `--target-row ID` | int | obbligatorio | obbligatorio; deve esistere e non contenere già il pannello | Riga di destinazione |

```bash
grafana-utils move-panel dashboard.json --panel-id 82 --target-row 81 -o out.json
# Pannello 82 spostato nella riga 81.
```

`gridPos` non viene ricalcolato: usare `reflow` dopo lo spostamento se serve un layout pulito.

### replace

Applica sostituzioni testuali a `target[*].expr`.

```bash
grafana-utils replace FILE --replace OLD=NEW [--row ID] [opzioni]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--replace OLD=NEW` | ripetibile, obbligatorio | nessuno | obbligatorio; ripetibile | Sostituzione applicata alle query |
| `--row ID` | int | intera dashboard | opzionale; se presente deve esistere; indipendente | Limita a una riga |

```bash
# 38 target contengono "checkup-app" nella query
grafana-utils replace dashboard.json --replace checkup-app=checkup-bff
# Sostituzioni applicate a 38 target.

# stesso token, ma solo nella riga 72
grafana-utils replace dashboard.json \
    --replace request_counter=req_total --row 72 -o out.json
```

`OLD=NEW` viene spezzato al primo `=`; `OLD` non può quindi contenere `=`. Le sostituzioni multiple si applicano nell'ordine indicato.

### transform

Modifica i pannelli che corrispondono a un tipo e/o a una regex sul titolo.

```bash
grafana-utils transform FILE [--match-type TIPO] [--match-title REGEX] [opzioni]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--match-type TIPO` | stringa | nessuno | almeno uno tra `--match-type` e `--match-title`; se entrambi, AND | Confronto con `type`, case-insensitive |
| `--match-title REGEX` | stringa | nessuno | almeno uno tra `--match-type` e `--match-title`; se entrambi, AND | `re.search` sul titolo, case-insensitive |
| `--replace OLD=NEW` | ripetibile | vuoto | opzionale; indipendente | Sostituzioni su `target[*].expr` |
| `--ds-uid UID` | stringa | nessuno | opzionale; indipendente | Imposta `datasource.uid` su pannello e target |
| `--ds-type TIPO` | stringa | `prometheus` | richiede `--ds-uid`; senza viene ignorato | Imposta `datasource.type` |
| `--new-title TESTO` | stringa | nessuno | opzionale; indipendente; si applica a tutti i pannelli matchati | Sovrascrive il titolo dei pannelli matchati |

```bash
# 42 pannelli timeseries, tutti modificati
grafana-utils transform dashboard.json --match-type timeseries \
    --ds-uid prom-new --ds-type prometheus -o out.json
# Pannelli corrispondenti: 42. Modificati: 42.

# 6 tabelle, tutte modificate
grafana-utils transform dashboard.json --match-title "^tabella" \
    --ds-uid prom-new
```

Opera sui pannelli di contenuto: le righe non vengono toccate.

### prune

Rimuove pannelli per id, titolo o tipo. Le righe non vengono mai rimosse.

```bash
grafana-utils prune FILE [--panel-id ID] [--match-title REGEX] [--match-type TIPO] [opzioni]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--panel-id ID` | int, ripetibile | nessuno | almeno uno tra i tre criteri; ripetibile; OR con gli altri | ID del pannello da rimuovere |
| `--match-title REGEX` | stringa | nessuno | almeno uno tra i tre criteri; OR con gli altri | Rimuove i pannelli con titolo corrispondente, case-insensitive |
| `--match-type TIPO` | stringa | nessuno | almeno uno tra i tre criteri; OR con gli altri | Rimuove i pannelli di quel tipo, case-insensitive |

```bash
grafana-utils prune dashboard.json --panel-id 97 --panel-id 98 -o out.json
# Pannelli rimossi: 2.

grafana-utils prune dashboard.json --match-title "^tabella riassuntiva" -o out.json
grafana-utils prune dashboard.json --match-type text --dry-run
```

### set-datasource

Cambia `uid` e, se richiesto, `type` del datasource su pannelli e target.

```bash
grafana-utils set-datasource FILE --uid UID [--type TIPO] [--row ID] [--force] [opzioni]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--uid UID` | stringa | obbligatorio | obbligatorio; nessuna dipendenza | Nuovo `datasource.uid` |
| `--type TIPO` | stringa | invariato | opzionale; indipendente; con `--force` determina il type creato (default `prometheus`) | Nuovo `datasource.type` |
| `--row ID` | int | intera dashboard | opzionale; se presente deve esistere | Limita a una riga |
| `--force` | flag | off | opzionale; indipendente; unico modo per creare un blocco `datasource` mancante | Crea il blocco `datasource` se assente |

```bash
grafana-utils set-datasource dashboard.json --uid prom-new -o out.json
# Datasource aggiornato in 154 punti.

grafana-utils set-datasource dashboard.json --uid prom-new --type prometheus \
    --row 69 --force -o out.json
```

Senza `--force` i pannelli privi di blocco `datasource` vengono saltati.

### reflow

Ricalcola `gridPos` dei pannelli sulla griglia della dashboard.

```bash
grafana-utils reflow FILE [--row ID] [--columns N] [--default-width N] [--default-height N] [opzioni]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--row ID` | int | tutte le righe | opzionale; se presente deve esistere | Limita a una riga |
| `--columns N` | int | `24` | opzionale; deve essere maggiore di 0 | Larghezza della griglia |
| `--default-width N` | int | `12` | opzionale; usato solo se `gridPos.w` manca | Larghezza di default |
| `--default-height N` | int | `8` | opzionale; usato solo se `gridPos.h` manca | Altezza di default |

```bash
grafana-utils reflow dashboard.json -o out.json
# Reflow applicato a 46 pannelli.

grafana-utils reflow dashboard.json --row 72 --columns 24 \
    --default-width 12 --default-height 8 -o out.json
```

Per ogni riga `x` riparte da 0; se il pannello supera `--columns` va a capo. I pannelli top-level fuori riga non vengono toccati.

### append-row

Aggiunge una riga parametrizzata, presa da un template o da un'altra dashboard.

```bash
grafana-utils append-row FILE [opzioni]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `FILE` | path | obbligatorio | obbligatorio; nessuna dipendenza | Dashboard JSON |
| `--template PATH` | path | `templates/system-view.row.tpl.json` | opzionale; usato solo senza `--from-dashboard` | Template della riga |
| `--from-dashboard PATH` | path | nessuno | opzionale; se presente prevale su `--template`; il file deve esistere | Estrae la riga da questa dashboard |
| `--row-match REGEX` | stringa | `(VISTA\s+SISTEMISTICA \| Sistemistica)` | sempre usato per `--on-existing`; con `--from-dashboard` seleziona anche la riga da copiare | Regex sul titolo della riga, case-insensitive |
| `--params PATH` | path | nessuno | opzionale; le chiavi sono i nomi dei placeholder; i valori CLI prevalgono e i vuoti/`null` del file vengono ignorati | File JSON o YAML con i valori dei placeholder |
| `--namespace TESTO` | stringa | `universo-on-line-feu-up` | opzionale; entra nel default di `--row-title` | Valore per `${NAMESPACE}` |
| `--cluster-gen TESTO` | stringa | `2` | opzionale; ha effetto solo se il template contiene `${CLUSTER_GEN}` | Valore per `${CLUSTER_GEN}` |
| `--datasource UID` | stringa | `QEIISg1Vz` | opzionale; ha effetto solo se il template contiene `${DATASOURCE_UID}` | Valore per `${DATASOURCE_UID}` |
| `--title-prefix TESTO` | stringa | vuoto | opzionale; ha effetto solo se il template contiene `${TITLE_PREFIX}` | Valore per `${TITLE_PREFIX}` |
| `--row-title TESTO` | stringa | `VISTA SISTEMISTICA - <NAMESPACE>` | opzionale; sovrascrive il default | Valore per `${ROW_TITLE}` |
| `--replace OLD=NEW` | ripetibile | vuoto | opzionale; indipendente | Sostituzioni su `target[*].expr` |
| `--base-id N` | int | `max + 1` | opzionale; errore se collide con id esistenti | ID base della nuova riga |
| `--position {top,bottom}` | scelta | `bottom` | opzionale; indipendente | Posizione della riga |
| `--on-existing {replace,skip,append,error}` | scelta | `replace` | ha effetto solo se `--row-match` trova una riga | Comportamento se esiste già una riga che matcha |
| `--collapsed` | flag | attivo | opzionale; esclude `--expanded` | Riga collassata |
| `--expanded` | flag | off | opzionale; esclude `--collapsed`; prevale l'ultimo flag | Riga espansa (figli top-level subito dopo) |
| `--no-normalize` | flag | off | opzionale; indipendente | Non converte `namespace="..."` in `namespace=~"..."` |
| `--dedupe-titles` | flag | off | opzionale; indipendente | Rende unici i titoli di riga e pannelli creati |

```bash
# dal template predefinito, con i valori di default
grafana-utils append-row dashboard.json -o out.json
# Row esistente 'VITA - VISTA PV - Sistemistica --> GEN2' rimossa.
# Row 'VISTA SISTEMISTICA - universo-on-line-feu-up' aggiunta (id 227..242, 16 pannelli).

# da un'altra dashboard, con namespace e cluster personalizzati
grafana-utils append-row dashboard.json \
    --from-dashboard altra.json --row-match "Sistemistica" \
    --namespace pa-digital --cluster-gen 3 -o out.json

# parametri in un file JSON o YAML
grafana-utils append-row dashboard.json --params params.json -o out.json

# posizione in cima e riga espansa
grafana-utils append-row dashboard.json --position top --expanded -o out.json
```

Formato del file `--params` (JSON o YAML):

```json
{
  "NAMESPACE": "pa-digital",
  "CLUSTER_GEN": "3",
  "DATASOURCE_UID": "QEIISg1Vz",
  "TITLE_PREFIX": "PA-DIGITAL ",
  "ROW_TITLE": "PA-DIGITAL - Sistemistica"
}
```

Con `--on-existing replace` la riga esistente viene rimossa insieme ai pannelli che le appartengono.

### extract-row

Estrae una riga in una dashboard autonoma.

```bash
grafana-utils extract-row --from-dashboard PATH [opzioni]
```


| Opzione | Tipo | Default | Obbligo / dipendenze | Descrizione |
| --- | --- | --- | --- | --- |
| `--from-dashboard PATH` | path | obbligatorio | obbligatorio; il file deve esistere | Dashboard sorgente |
| `--row-match REGEX` | stringa | `(VISTA\s+SISTEMISTICA \| Sistemistica)` | almeno uno tra `--row-match` e `--row-id`; se entrambi, vince `--row-id` | Regex sul titolo, case-insensitive |
| `--row-id ID` | int | nessuno | almeno uno tra `--row-match` e `--row-id`; se presente prevale | ID della riga |
| `--title TESTO` | stringa | titolo della row | opzionale; indipendente; viene reso unico | Titolo della dashboard di output |
| `--uid UID` | stringa | generato | opzionale; se esplicito non deve comparire in `--existing-dashboards` | uid della dashboard di output |
| `--existing-dashboards FILE` | path | nessuno | opzionale; se presente, uid e titoli letti dal file contano come occupati | Inventario JSON delle dashboard già in Grafana |
| `--panel-id-base N` | int | `max id sorgente + 1` | opzionale; deve essere almeno 1 | Primo id dei pannelli |
| `--dedupe-titles` | flag | off | opzionale; indipendente | Rende unici i titoli dei pannelli |

```bash
grafana-utils extract-row \
    --from-dashboard examples/full_dashbaord.json \
    --row-match "Sistemistica" \
    -o sistemistica.json
# Row 'VITA - VISTA PV - Sistemistica --> GEN2' estratta con 16 pannelli (id 227..243).
# Dashboard di output: uid 'axBwMw6CU', titolo 'VITA - VISTA PV - Sistemistica --> GEN2'.
```

Con l'inventario delle dashboard esistenti il tool evita collisioni di `uid` e titolo:

```bash
curl -s "$GRAFANA/api/search?type=dash-db" \
    -H "Authorization: Bearer $TOKEN" > inventario.json

grafana-utils extract-row \
    --from-dashboard examples/full_dashbaord.json \
    --row-match "Sistemistica" \
    --existing-dashboards inventario.json -o estratta.json
# titolo 'VITA - VISTA PV - Sistemistica --> GEN2 (2)' se il nome è già usato
```

La dashboard prodotta ha `id: null`, `version: 1` e un `uid` nuovo; gli id dei pannelli partono dopo l'ultimo id della sorgente. Un `--uid` già presente in inventario è un errore.

## Pipeline di esempio

Ogni passaggio legge un file e ne scrive un altro, senza mai perdere lo stadio precedente:

```bash
# 1. estrai la vista in una dashboard autonoma
grafana-utils extract-row --from-dashboard dashboard.json \
    --row-match "Sistemistica" -o build/vista.json

# 2. aggiorna il datasource e normalizza i titoli
grafana-utils transform build/vista.json --match-type timeseries \
    --ds-uid prom-new --ds-type prometheus -o build/vista-prom.json

# 3. rimuovi i pannelli di testo e rifai il layout
grafana-utils prune build/vista-prom.json --match-type text -o build/pulita.json
grafana-utils reflow build/pulita.json -o build/finale.json

# 4. valida il risultato
grafana-utils validate build/finale.json --severity warning
```

In CI la validazione finale non va disattivata: il file viene scritto comunque e il suffisso `_ERROR_<TIPO>` segnala l'artefatto problematico.

```bash
grafana-utils transform dashboard.json --match-type timeseries \
    --ds-uid prom-new -o build/dashboard.json
rc=$?
if [ "$rc" -ne 0 ]; then
    echo "validazione fallita, vedi out/lint_error_*.txt"
    exit "$rc"
fi
```

## Errori e log

Ogni errore viene classificato e registrato in `out/` con un nome `<tipo>_error_<AAAAMMGG-HHMMSS>.txt`. La directory si sposta con la variabile `GRAFANA_TOOL_LOG_DIR`.


| Tipo               | Quando                                            | Exit |
| -------------------- | --------------------------------------------------- | ------ |
| `INPUT_ERROR`      | File assente, JSON non valido, radice non oggetto | 2    |
| `OUTPUT_ERROR`     | Path non scrivibile o directory al posto del file | 3    |
| `COMMAND_ERROR`    | Errore logico del comando, `--replace` malformato | 1    |
| `USAGE_ERROR`      | Argomenti mancanti o opzioni sconosciute          | 2    |
| `VALIDATION_ERROR` | ID duplicati o mancanti dopo la scrittura         | 1    |
| `LINT_ERROR`       | Issue con severità pari o superiore alla soglia  | 1    |

Un log mancante non maschera mai l'errore originale.

## Sviluppo

La suite usa solo `unittest`:

```bash
python3 -m unittest discover -s tests -t . -v
```

Per architettura dei moduli, pipeline interna, regole del linter e dettagli implementativi la documentazione di riferimento è [AGENTS.md](AGENTS.md).
