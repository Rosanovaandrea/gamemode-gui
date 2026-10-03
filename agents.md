# Agents.md — Riepilogo del lavoro su GameMode GUI

Questo documento riassume tutto il lavoro svolto sul progetto **GameMode GUI**,
un'applicazione desktop (GTK4 + Libadwaita + Python 3) per gestire in modo
visuale, sicuro e dichiarativo il file di configurazione `gamemode.ini` del
daemon **Feral GameMode**.

L'enfasi è sulle **scelte architetturali** che abbiamo preso lungo il percorso,
sul *perché* le abbiamo prese, e su come il codice le riflette.

---

## 1. Contesto e obiettivo

- Gestire **tutte** le opzioni di `gamemode.ini` da una GUI.
- Strategia di scrittura **sicura**: backup, rollback, reset, scrittura atomica.
- Generazione del file INI con un **approccio dichiarativo tabellare**
  (tabella di `OptionSpec` + renderer), non con `configparser` (che perderebbe
  i commenti). Il file viene sempre ricostruito per intero.
- Flusso utente a **schede** (Generale / Filtro / GPU / Riepilogo / Daemon) con
  salvataggio per scheda.
- Test/utility del daemon e gestione del gruppo utente `gamemode`.

Il repository contiene anche il **codice sorgente C di GameMode** (`gamemode/`),
usato come riferimento: il progetto GUI resta però **staccato** — non è un fork,
non compila niente di gamemode; si limita a generare e gestire il file di
configurazione.

---

## 2. Scelte architetturali principali

### 2.1 File unico in `/etc/gamemode.ini`

**Decisione**: la GUI gestisce **solo** `/etc/gamemode.ini`, non
`~/.config/gamemode.ini`.

**Perché**: il daemon di GameMode carica **4 file** in ordine e li fonde
(`gamemode-config.c`, `CONFIG_NUM_LOCATIONS=4`): `/usr/share/gamemode/gamemode.ini`
(spedito dal pacchetto, protected), `/etc/gamemode.ini` (protected),
`~/.config/gamemode.ini` e `$PWD/gamemode.ini` (unsafe). Le liste si accodano, i
valori scalari **sovrascrivono** → vince l'ultimo letto. La sezione `[gpu]`
(power state GPU, overclock NVIDIA/AMD) è accettata **solo** nelle posizioni
"protected" (`/etc`, `/usr/share/gamemode`); dai file unsafe viene scartata
(`if (!load_protected) { ... return 1; }`, con log "Consider moving this option
to /etc/gamemode.ini").

Si scrive in `/etc` (non in `/usr/share/gamemode`, che appartiene al pacchetto e
viene sostituito dagli aggiornamenti) perché è il percorso dell'amministratore,
viene letto dopo il file spedito (quindi ne sovrascrive i valori) e abilita la
sezione `[gpu]`. Conservare una config in `.config` E una in `/etc` sarebbe stato
confuso e inutile: un **unico file di override**, con tutti i privilegi che
comporta.

**Base installata**: la GUI rileva il file del pacchetto
(`core.resolve_base_path()`, da `$XDG_DATA_DIRS`/`/usr/share`, forzabile con
`GAMEMODE_BASE`) e lo usa come base: i valori mostrati sono quelli **effettivi**
(merge base + `/etc`, con liste accodate e scalari sovrascritti, come fa il
daemon). I commenti delle voci scritte in `/etc` arrivano dal file installato
quando presenti (`load_base_comments`). Al primo salvataggio senza `/etc`, il
`.orig` è seedato col contenuto del file installato, così "Ripristina originale"
torna ai default del pacchetto (il `commit` privilegiato accetta un path di seed).

Conseguenze:
- Tutte le scritture passano per un **helper privilegiato** (pkexec/sudo).
- La GUI chiede la password amministratore solo al momento del salvataggio
  (non all'avvio).
- La scheda **Riepilogo** mostra sia l'override gestito sia la base installata.

### 2.2 Commit atomico "copy-on-write" con backup e rollback

**Decisione**: riscrivere **sempre l'intero file** al salvataggio, seguendo la
strategia "copy on write":

1. contenuto nuovo scritto in `gamemode.ini.tmp` + `fsync`;
2. se esiste, il file attivo precedente è copiato in `gamemode.ini.bak`;
3. `os.replace(tmp, gamemode.ini)` → **rename atomico** su POSIX;
4. `gamemode.ini.orig` = copia "vergine" iniziale, creata **una sola volta** e
   mai riscritta automaticamente (ripristinabile);
5. in caso di errore al passo 3 → **rollback automatico** dal `.bak`;
6. pulizia del `.tmp` residuo.

Il file "precedente al commit" e il "tmp" sono volutamente **cose diverse**:
il tmp è solo il buffer di scrittura, il `.bak` è la fotografia del file attivo
che stiamo per sostituire.

Come si riflette nel codice:
- `privileged.py` esegue la strategia completa **come root**;
- `ConfigManager` (`core.py`) delega a `privileged.py` quando il percorso è
  `/etc`, oppure replica la stessa sequenza in locale per i test.

### 2.3 Helper privilegiato separato (`privileged.py`)

**Decisione**: un modulo **a sé stante**, invocato come subprocess con
`pkexec` (fallback `sudo -n`), che esegue `commit`/`restore-backup`/
`restore-orig`/`ensure-orig`.

**Perché**: la GUI gira come utente normale ma scrive in `/etc` (root-owned).
Tutte le operazioni di scrittura atomica e rollback devono avvenire in un
processo con i privilegi giusti. L'helper non deve importare il resto
dell'app: è un comando puro, leggibile e testabile.

### 2.4 Opzioni data-driven: `options.json` (single source of truth)

**Decisione**: ogni opzione di `gamemode.ini` è descritta **una volta sola**
come voce JSON in `options.json`, raccolta per categoria. Campi principali:

```
key             nome della chiave INI
description_id  chiave i18n della descrizione
value_type      int | float | bool | string | choice | list | enable
widget          stepper | switch | radio | list | entry
range           [min, max] per i numerici (null = illimitato)
choices         valori ammessi per "choice"
default         valore di default
special         true se i valori vanno letti dal sistema
special_source  sorgente dei valori speciali (es. "cpu_governors")
depends_on      id di un'altra opzione da cui dipende
comment         commento emesso nel file INI
```

`core.load_categories()` legge il file e costruisce le dataclass `Category` e
`OptionSpec`; da lì derivano `OPTIONS`, `SECTIONS_ORDER` e la creazione
**dinamica** delle schede in `ui.py`. Vantaggi:
- **aggiungere un'opzione = aggiungere una voce JSON** (nessun codice Python);
- l'output è deterministico: commenti e ordine preservati esattamente;
- il rendering è una **funzione pura**, testabile senza GUI/display;
- **ui e widget non hanno codice ad hoc per opzione**: `widgets.build_widget`
  mappa `value_type`/`widget` in un controllo GTK standard.

### 2.4b Valori speciali dal sistema

Alcune opzioni hanno `"special": true` e `special_source`:
- **governor CPU** (`desiredgov`, `defaultgov`, `igpu_desiredgov`):
  `get_cpu_governors()` legge `/sys/.../scaling_available_governors`;
- **core CPU** (`cpu.pin_cores`): `get_cpu_cores()` legge
  `/sys/devices/system/cpu/online` e fornisce l'elenco dei core.

`core.resolve_choices()` risolve la lista dei valori dal sistema (con fallback
statico). Il widget resta quello standard (`ChoicePicker`), tranne il pinning
che usa `CoresEditor` (checkbox). Aggiungere un `special_source` = una funzione
in `SPECIAL_SOURCES`.

### 2.5 Solo opzioni attive + dipendenze ([gpu]) + sessione

**Decisione**: ogni opzione ha un valore in memoria; **non esiste** un flag
esplicito. Un'opzione è "attiva" — e quindi scritta — **solo se il suo valore
differisce dal default** della tabella (o se è una lista non vuota). I default
non vengono scritti: GameMode li applica già da sé, quindi metterli nel file è
inutile. Un file con tutte le opzioni ai default equivale a un file vuoto.

Le opzioni facoltative rimaste vuote (es. `defaultgov=`) e le liste vuote sono
omesse.

**Dipendenze**: alcune opzioni hanno un campo `depends_on`. In particolare le
voci `[gpu]` dipendono da `apply_gpu_optimisations`: la scheda GPU espone un
interruttore **"Abilita modifica power plan GPU"** che, quando attivo, scrive
`apply_gpu_optimisations=accept-responsibility`. Se è spento, le altre voci
`[gpu]` sono disabilitate nella UI e non vengono scritte.

Interazione con la GUI:
- l'input è sempre attivo (tranne le opzioni dipendenti disabilitate);
- non c'è checkbox "Includi": l'attivazione è implicita nella modifica;
- la descrizione di ogni opzione è mostrata **direttamente sotto il controllo**
  (niente tooltip o popup).

Al commit, i valori correnti vengono salvati anche in
`gamemode.ini.session.json` accanto al file attivo, così la UI può ripartire
dalle ultime scelte anche se il file è stato modificato esternamente.

### 2.6 i18n tramite file esterni XML (mai stringhe hardcoded)

**Decisione**: tutte le stringhe visibili passano da `tr("chiave")`, che legge
da `locale/<lang>.xml`. Oggi esiste solo l'italiano (`locale/it.xml`), ma il
sistema è configurabile: basta aggiungere un altro file XML e impostare
`GAMEMODE_LANG` (o lasciarlo rilevare automaticamente dal sistema).

Formato:
```xml
<translations lang="it">
  <entry id="btn.save">Salva</entry>
</translations>
```

Se una chiave manca, `tr()` torna al nome della chiave: nessun crash.

### 2.7 Pochi file, interfaccia divisa per schede

**Decisione** (refactoring richiesto dall'utente): minimizzare i file. Da una
struttura iniziale a molteplici moduli (`core/` + `ui/` da ~15 file) siamo
passati a **6 file di codice**:

```
gamemode-gui/
├── main.py          entry point (delega a ui.main)
├── options.json     definizioni delle opzioni per categoria
├── core.py          logica pura (definizioni, valori speciali, renderer, config, i18n, daemon, sessione)
├── ui.py            tutta l'interfaccia GTK, schede generate dai dati
├── widgets.py       widget riutilizzabili (build_widget + componenti, vedi 2.8)
├── privileged.py    helper root per /etc
├── locale/it.xml    traduzioni
├── test_core.py     test della logica (senza display)
└── smoke_test.py    test dell'interfaccia (richiede DISPLAY, usa cartella temp)
```

`ui.py` è organizzata in "capitoli" numerati (1..8), con le schede come unità
principali, così è facile navigare il file.

### 2.8 Widget riutilizzabili in `widgets.py`

**Decisione**: raccogliere i componenti riutilizzabili in un modulo dedicato,
per non duplicare la costruzione dei widget tra le schede:

- **`build_widget`** — un unico punto che traduce `value_type`/`widget` della
  definizione JSON nel controllo GTK giusto (stepper/switch/radio/list/entry).
  Nessun codice ad hoc per opzione; le opzioni speciali differiscono solo per
  l'origine delle `choices`.
- **`ChoicePicker`** — **niente dropdown**: un gruppo di **radio button** in un
  FlowBox. Selezionare una voce disattiva le altre. È la scelta che ha risolto
  il problema dei menù a tendina (vedi 3.3).
- **`StepperBox`** — pulsanti **− / +** con etichetta centrale, vincolati a
  `min`/`max`, con supporto a step decimali (per i float).
- **`ListEditor`** — lista di stringhe (whitelist/blacklist, script custom
  start/end).
- **`CoresEditor`** — checkbox per selezionare i core (pinning CPU); valore =
  lista dei core selezionati.
- **`OptionRow`** — riga completa: **nome opzione + descrizione** sulla stessa
  riga ("nome: descrizione") e **sotto il selettore**; padding interno per dare
  respiro alle righe.

Tutti espongono la stessa interfaccia valori: `get_value()`, `set_value()`,
`set_sensitive()`, callback `on_change`.

### 2.9 `ioprio` come scelta a pulsanti (0–7, off, reset)

**Decisione**: `ioprio` è di tipo **`choice`** con widget **`radio`**
(`ChoicePicker`), non più uno stepper numerico. Valori: da `0` (massima) a `7`,
più i valori speciali `off` (disabilita) e `reset` (ripristina il comportamento
predefinito basato sulla priorità CPU).

Il file scrive letteralmente `ioprio=reset` (e `ioprio=off`), coerente con la
descrizione mostrata all'utente e con il commento di `example/gamemode.ini`.

---

## 3. Bug reali trovati e risolti (lezione importante)

### 3.1 L'app non partiva

- `GameModeWindow.__init__` non accettava `application=` come kwarg → crash
  immediato.
- `Adw` importato senza `gi.require_version` prima dei widget.
- `ViewStack.set_transition_type` non esiste nella versione di libadwaita in
  uso → guardato con `hasattr`.
- `Adw.EntryRow` non ha `set_placeholder_text` → sostituito con `Gtk.Entry`.

### 3.2 Crash al "Riavvia gamemoded"

`dlg.present(self)`: in GTK4 `Gtk.Window.present()` **non accetta argomenti**.
Corretti tutti i `present(self)` → `present()`.

### 3.3 I menù a tendina non si vedevano / non erano modificabili

Due cause combinate:
1. le `ComboRow` partivano **disabilitate** (`set_sensitive(False)`) perché il
   flag "Includi" è `False` all'avvio → al click non succedeva nulla;
2. il popover delle combo non si posizionava bene dentro i riquadri
   (altezza/posizionamento).

**Soluzione architetturale** (non una toppa): eliminare i dropdown e passare ai
**radio button** (`ChoicePicker`) e agli **stepper** (`StepperBox`). Niente più
popup = niente più problemi di posizionamento. Gli input sono **sempre attivi**:
una modifica attiva automaticamente il flag.

### 3.4 Toggle e switch a tutta larghezza

Gli `Gtk.Switch` come figli di un `Box` verticale venivano stirati
orizzontalmente. Corretti con `halign=START`, `hexpand=False`.

---

## 4. Flusso utente (5 schede)

| Scheda | Contenuto |
|------|-----------|
| 1 | **Generale** (`[general]`): governor, profili, renice, ioprio, ecc. |
| 2 | **Filtro** (`[filter]`): whitelist / blacklist |
| 3 | **GPU** (`[gpu]`): interruttore "Abilita modifica power plan GPU" + power state NVIDIA/AMD (attivi solo con l'interruttore), con banner di avviso |
| 4 | **CPU** (`[cpu]`): pinning dei core (checkbox) e parking dei core (switch) |
| 5 | **Custom** (`[custom]`): script di start/end (liste) + timeout |
| 6 | **Riepilogo**: anteprima del file completo + Salva, Ripristina backup, Ripristina originale |
| 7 | **Daemon**: test/riavvio del daemon `gamemoded` + gestione gruppo `gamemode`, con **console simulata** sempre visibile |

Navigazione con `Adw.ViewStack` + `Adw.ViewSwitcher` nell'header: si passa
liberamente da una scheda all'altra senza ordine forzato. Ogni scheda di
opzioni (Generale, Filtro, GPU) e il Riepilogo hanno il proprio pulsante
**Salva**, che riscrive comunque l'intero file; la scheda Daemon non salva.
Stato delle scelte mantenuto in memoria (solo valori).

---

## 5. Comandi e utility

- **Test daemon**: `gamemoded -t` e `gamemoderun --version` (pulsante "Esegui
  test del daemon" nella scheda **Daemon**). L'output dei comandi — come quello
  di riavvio e aggiunta al gruppo — è mostrato in una **console simulata**
  sempre visibile nella scheda, senza popup né verdetti di successo/errore.
- **Riavvio daemon**: `systemctl --user restart gamemoded`.
- **Gruppo `gamemode`**: verifica appartenenza; pulsante "Aggiungi al gruppo"
  che esegue `usermod -aG gamemode $USER` via pkexec; promemoria di
  logout/login dopo l'aggiunta (mostrato **solo in caso di successo**).

Tutti i comandi usano liste di argomenti (`subprocess`), mai `shell=True`.

---

## 6. Testing

- **`test_core.py`** (senza display): renderer/roundtrip, liste ripetute,
  commit locale atomico + `.orig`/`.bak`/rollback, i18n XML, sessione JSON,
  `privileged.py` in locale.
- **`smoke_test.py`** (con DISPLAY): crea la finestra reale, verifica le schede,
  modifica un valore, salva su un percorso temporaneo (`GAMEMODE_CONFIG`),
  verifica `.orig` e `.session.json` creati e che il file sia completo.
- L'app va lanciata con `python3 main.py`; per i test su percorso scrivibile:
  `GAMEMODE_CONFIG=/tmp/prova/gamemode.ini python3 main.py`.

---

## 7. Indagine: configurazione per singolo gioco? (informativa)

Richiesta informativa documentata e conclusa (nessuna implementazione):

- **Non esiste** una config "per singolo eseguibile" in GameMode: la config è
  unica e globale, con **merging** tra più file in ordine di priorità
  (`$PWD` → `$XDG_CONFIG_HOME` → `/etc` → `/usr/share/gamemode`).
- Il "local data `$PWD`" è risolto alla **directory di lavoro del daemon**
  (`get_current_dir_name()` in `gamemode-config.c`), non per gioco.
- Il vero filtro "per programma" è `[filter] whitelist/blacklist` (nomi di
  eseguibile): solo accettazione/rifiuto dell'attivazione, non valori diversi
  per gioco.
- Esiste l'API supervisore (`gamemode_request_start_for`) per richieste
  programmatiche per-PID da un launcher custom.
- Il modo pratico per attivare GameMode su un singolo gioco è
  `gamemoderun %command%` nelle opzioni di lancio di Steam (e
  `GAMEMODERUNEXEC` per wrapper come optirun/DRI_PRIME).

La nostre GUI gestisce il file **globale** (`/etc/gamemode.ini`), che è
l'impostazione che GameMode supporta nativamente.

---

## 8. Stato di avanzamento / possibile lavoro futuro

Fatto:
- [x] Tabella dichiarativa completa (`[general]`, `[filter]`, `[gpu]`)
- [x] Unico file in `/etc` con helper privilegiato (pkexec/sudo)
- [x] Scrittura atomica + backup + rollback + `.orig`
- [x] i18n via XML (italiano, configurabile)
- [x] Stato di sessione persistito su JSON
- [x] Widget riutilizzabili (radio picker, stepper, list editor)
- [x] Interfaccia a schede con salvataggio per scheda, test utility, gruppo utente
- [x] Test logica + smoke test interfaccia

Possibili prossimi passi (non concordati):
- [ ] Selettore di lingua nel menu Aiuto
- [ ] Profili predefiniti esportabili/importabili
- [ ] Integrazione di una sezione per-gioco via `gamemoderun`/wrapper
- [ ] Copertura `.po`/`.pot` per gettext (attualmente XML custom)