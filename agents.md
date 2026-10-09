# Agents.md — Riepilogo del lavoro su GameMode GUI

Questo documento riassume tutto il lavoro svolto sul progetto **GameMode GUI**,
un'applicazione desktop (GTK4 + Libadwaita + Python 3) per gestire in modo
visuale, sicuro e dichiarativo il file di configurazione `gamemode.ini` del
daemon **Feral GameMode**.

L'enfasi è sulle **scelte architetturali** che abbiamo preso lungo il percorso,
sul *perché* le abbiamo prese, e su come il codice le riflette.

---

## 1. Contesto e obiettivo

<<<<<<< HEAD
- Gestire **tutte** le opzioni di `gamemode.ini` da una GUI.
- Strategia di scrittura **sicura**: backup, rollback, reset, scrittura atomica.
- Generazione del file INI con un **approccio dichiarativo tabellare**
  (tabella di `OptionSpec` + renderer), non con `configparser` (che perderebbe
  i commenti). Il file viene sempre ricostruito per intero.
- Flusso utente a **schede** (Generale / GPU / CPU / Custom / Riepilogo /
  Daemon) con salvataggio per scheda.
- Test/utility del daemon e gestione del gruppo utente `gamemode`.

Il repository contiene anche il **codice sorgente C di GameMode** (`gamemode/`),
usato come riferimento: il progetto GUI resta però **staccato** — non è un fork,
non compila niente di gamemode; si limita a generare e gestire il file di
configurazione.
=======
- **Project**: a desktop GUI (GTK4 + Libadwaita, Python 3) to manage the
  `gamemode.ini` configuration file of the **Feral GameMode** daemon.
- **Repository layout**:
  - `gamemode/` — the upstream **C source of GameMode**, used only as a reference
    (not a fork; nothing of it is compiled). It documents the config locations, the
    `[gpu]` "protected" rules and the CLI of the daemon.
  - `gamemode-gui/` — the application itself (this repo).
- **Goal**: manage **all** `gamemode.ini` options from a GUI, with a **safe write
  strategy** (atomic commit, backup, rollback, restore), a **declarative/tabular**
  INI generation (no `configparser`, so comments are preserved), a **tabbed** user
  flow, and daemon utilities (test, restart, `gamemode` group).
- **Codebase language**: source code, comments, docstrings, `README.md` and this
  file are in **English**. Only the translation data (`locale/*.xml`) and the
  desktop entry's localised fields (`Comment[it]`) are in other languages.
>>>>>>> 1b8b488 (English codebase (comments/docstrings) + refactoring)

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
value_type      int | float | bool | string | choice | list | cores | enable | toggle_entry
widget          stepper | switch | radio | list | cores | entry
range           [min, max] per i numerici (null = illimitato)
choices         valori ammessi per "choice"
default         valore di default
special         true se i valori vanno letti dal sistema
special_source  sorgente dei valori speciali (es. "cpu_governors")
depends_on      id di un'altra opzione da cui dipende
comment         commento emesso nel file INI
target/entry    per "toggle_entry": l'interruttore aggiunge/rimuove `entry` dalla lista `target`
```

A livello di categoria, `toggle_card_id` è il titolo (i18n) della card che
raccoglie le opzioni `toggle_entry` in cima alla scheda (es. le notifiche
`notify-send` in `[custom]`).

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
da `locale/<lang>.xml`. L'elenco delle lingue non è hardcoded: si legge dalla
chiave `supported_langs` di `~/.config/gamemode-gui/settings.json` (default
`it`, `en`) e ogni voce è validata sull'esistenza di `locale/<codice>.xml`. Le
voci non valide (codice errato, file mancante, JSON rotto) vengono ignorate e
segnalate senza bloccare l'app. Il nome mostrato nel menu viene dall'attributo
`name` dell'XML. La lingua si sceglie in quest'ordine: scelta salvata
dall'utente (`lang`, menu nell'header, ha la precedenza su tutto), poi il locale
di sistema (LC_ALL > LC_MESSAGES > LANG), altrimenti inglese. Per aggiungere una
lingua: nuovo file XML + codice in `supported_langs`.

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
passati a **6 moduli Python** (più i dati: `options.json`, `style.css`):

```
gamemode-gui/
├── main.py          entry point (delega a ui.main)
├── options.json     definizioni delle opzioni per categoria
├── presentation.json contenuti della scheda Presentazione (data-driven)
├── core.py          logica pura (definizioni, valori speciali, renderer, config, i18n, daemon, sessione)
├── ui.py            tutta l'interfaccia GTK, schede generate dai dati
├── widgets.py       widget riutilizzabili (build_widget + componenti, vedi 2.8)
├── privileged.py    helper root per /etc
├── fileops.py       scrittura atomica/backup/rollback condivisa (GUI + root)
├── style.css        stile dell'app (CSS caricato a runtime)
├── locale/it.xml    traduzioni (italiano)
├── locale/en.xml    traduzioni (inglese)
├── test_core.py     test della logica (senza display)
└── smoke_test.py    test dell'interfaccia (richiede DISPLAY, usa cartella temp)
```

<<<<<<< HEAD
`ui.py` è organizzata in "capitoli" numerati (1..8), con le schede come unità
principali, così è facile navigare il file.
=======
`ui.py` is organised in numbered "chapters" (1..8, plus a 5b for the Presentation
tab), with the tabs as the main units, so the file is easy to navigate. `core.py`
is pure logic (no GTK), fully testable without a display.
>>>>>>> 1b8b488 (English codebase (comments/docstrings) + refactoring)

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
- **`ListEditor`** — lista di stringhe (script custom start/end).
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

<<<<<<< HEAD
Il file scrive letteralmente `ioprio=reset` (e `ioprio=off`), coerente con la
descrizione mostrata all'utente e con il commento di `example/gamemode.ini`.
=======
Current categories/options (25 options across 4 sections):
`[general]` (12), `[gpu]` (6), `[cpu]` (2), `[custom]` (5, including the two
`toggle_entry` notification switches).

### 2.3 Special values read from the system

Some options have `"special": true` and a `special_source`:

- **CPU governor** (`general.desiredgov`, `general.defaultgov`,
  `general.igpu_desiredgov`): `get_cpu_governors()` reads
  `/sys/devices/system/cpu/cpu*/cpufreq/scaling_available_governors` (**all** CPUs,
  deduplicated) with a static fallback. Note: GameMode applies `igpu_desiredgov`
  through the same `cpugovctl` as the CPU governor, so it is the same value domain.
- **CPU cores** (`cpu.pin_cores`): `get_cpu_cores()` reads
  `/sys/devices/system/cpu/online` (fallback: `os.cpu_count()`).

`core.resolve_choices()` resolves the list from the system; the widget stays
standard (`ChoicePicker`), except pinning which uses `CoresEditor` (checkboxes).
Adding a `special_source` = adding a function to `SPECIAL_SOURCES`.

### 2.4 Presentation — `presentation.json`

The Presentation tab is not options: it is a text page split into blocks. The
**structure** (which blocks, in what order, which are warnings) lives in
`presentation.json`; the **texts** live in the language files. Adding a block =
one JSON entry + i18n keys. Current blocks: *What is GameMode*, *Why GameMode GUI*,
*Launching a game with gamemoderun*, *Steam*, *Lutris*, *Disclaimer* (warning card
with icon).

### 2.5 Config management + privileged helper

**Single file `/etc/gamemode.ini`**: the daemon loads 4 files and merges them
(`gamemode-config.c`): `/usr/share/gamemode/gamemode.ini` (protected),
`/etc/gamemode.ini` (protected), `~/.config/gamemode.ini` and `$PWD/gamemode.ini`
(unsafe). Lists are appended, scalars override → last read wins. The `[gpu]`
section is accepted **only** in the "protected" locations, so the GUI writes to
`/etc` (not `/usr/share`, which belongs to the package).

- **Base**: `core.resolve_base_path()` detects the installed file
  (`$XDG_DATA_DIRS`/`/usr/local/share`/`/usr/share`, forceable with
  `GAMEMODE_BASE`); the shown values are the **effective** ones (base + `/etc`
  merge), and the comments of the `/etc` entries come from the installed file.
- **Atomic commit** ("copy on write"): `.tmp` + `fsync` → `.bak` of the previous
  active file → `os.replace` (atomic) → `.orig` (pristine, created once) → on
  error, automatic rollback from `.bak`.
- **`fileops.py`** holds this logic once; it is used by **both** the local path
  (`core.ConfigManager`, writable paths / tests) **and** the privileged helper.
- **`privileged.py`** is a standalone command (no import of the app), run as root
  via `pkexec` (fallback `sudo -n`); it handles `commit`/`restore-backup`/
  `restore-orig`/`ensure-orig` and reads stdin for the new content (and an optional
  seed path).

### 2.6 Active options, dependencies and session

- **Only active options are written**: an option is written only if its value
  differs from the default (or a list is non-empty). Defaults are not written
  because GameMode applies them itself; a file with all defaults equals an empty
  file.
- **Dependencies**: `[gpu]` options have `depends_on: gpu.apply_gpu_optimisations`;
  the GPU tab has an **"Enable GPU power plan editing"** switch that writes
  `apply_gpu_optimisations=accept-responsibility`. When it is off, the other
  `[gpu]` entries are disabled in the UI and not written.
- **Session**: at commit, the current values are also saved to
  `gamemode.ini.session.json` next to the active file, so the UI can start from the
  last choices even if the file was changed externally. `core.coerce_value()`
  converts JSON values back to the spec type.

### 2.7 i18n and language selection

- All visible strings go through `tr("key")`, which reads `locale/<lang>.xml`.
  XML texts may use `\n` for line breaks (converted on load).
- The list of available languages is **not hardcoded**: it is read from
  `supported_langs` in `~/.config/gamemode-gui/settings.json` (default `it`, `en`)
  and each entry is validated against the existence of `locale/<code>.xml`. Invalid
  entries are ignored and reported (non-blocking). The menu label comes from the
  XML `name` attribute.
- Language resolution order: **saved user choice** (`lang` in `settings.json`, set
  from the header menu; wins over everything) → **system locale**
  (`LC_ALL > LC_MESSAGES > LANG`, only `it`/`en`) → **English**.
- The settings file is created on first run; missing/broken entries fall back to
  safe defaults without blocking the app.

### 2.8 Reusable widgets — `widgets.py`

- **`build_widget`** — single point that maps `value_type`/`widget` to the right GTK
  control; no per-option code.
- **`ChoicePicker`** — **no dropdown**: a group of radio buttons in a FlowBox
  (selected item highlighted with the accent colour, GNOME "segmented" style).
- **`StepperBox`** — `−`/`+` buttons with a central label, bounded by `min`/`max`,
  decimal steps for floats (the `+`/`−` texts use the accent colour).
- **`SwitchBox`** — on/off switch with the same value interface as the others (also
  used for `enable`/`toggle_entry`).
- **`ListEditor`** — list of strings (custom start/end scripts).
- **`CoresEditor`** — checkboxes to select CPU cores (pinning); value = selected
  cores.
- **`OptionRow`** — full row: *name + description* on the same line and the control
  below; no per-type special-casing (uniform `get_value`/`set_value`).

All expose the same value interface: `get_value()`, `set_value()`,
`set_sensitive()`, `on_change` callback.

### 2.9 UI tabs

`Adw.ViewStack` + `Adw.ViewSwitcher` in the header; free navigation, no forced
order. The Presentation tab opens by default.

| # | Tab | Content |
|---|-----|---------|
| 1 | **Presentation** (default) | What GameMode is, why the GUI, `gamemoderun`/Steam/Lutris, disclaimer. Data-driven from `presentation.json` + i18n |
| 2 | **General** (`[general]`) | governor, profiles, renice, ioprio, iGPU, etc. |
| 3 | **GPU** (`[gpu]`) | "Enable GPU power plan editing" switch + NVIDIA/AMD power state (active only with the switch), with a warning banner |
| 4 | **CPU** (`[cpu]`) | core pinning (checkboxes) and core parking (switch) |
| 5 | **Custom** (`[custom]`) | **Notifications** card (two `toggle_entry` switches) + start/end scripts (lists) + timeout |
| 6 | **Summary** | preview of the full file + Save, Restore backup, Restore original |
| 7 | **Daemon** | daemon test/restart + `gamemode` group management, with an always-visible **simulated console** |

Each options tab and the Summary have their own **Save** button that rewrites the
whole file; the Daemon tab does not save. After a save, a dialog reminds the user to
**restart the daemon** (Daemon tab) for the changes to take effect.
>>>>>>> 1b8b488 (English codebase (comments/docstrings) + refactoring)

### 2.10 Type rules — single dispatch table

The type-specific logic — how a value is rendered to INI, whether it is written,
how it is parsed from INI and how it is coerced from the JSON session — is
centralised in a single dispatch table `TYPE_RULES` (`core.py`), keyed by
`value_type`. Each entry is a `TypeRules` object with four callables: `render`,
`is_written`, `parse_ini`, `coerce_json`. `render_option()`, `is_written()`,
`values_from_parsed()` and `coerce_value()` all dispatch through `_rules(spec)`,
so adding or changing a value type is a one-place change.

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

<<<<<<< HEAD
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
=======
- Binaries (`gamemoded`, `systemctl`, `usermod`, `pkexec`, `sudo`, `pkill`) are
  resolved to **absolute paths** (`shutil.which` + known fallbacks), so they work
  even with a minimal PATH (e.g. under `pkexec`) or different layouts (`/usr/sbin`
  vs `/sbin`, merged-usr).
- The version is read from **`gamemoded --version`** (NOT `gamemoderun --version`:
  `gamemoderun` is a script that execs the passed command and does not handle
  `--version`).
- `CommandResult.command` records the command actually run, and the Daemon console
  shows it (useful to diagnose distro differences).
- Debian separates the daemon into `gamemode-daemon`; the `.deb` `Depends` is
  `gamemode-daemon | gamemode` (compatible with older single-package Debian too).
- CPU governors are read from all `.../cpu*/cpufreq/scaling_available_governors`.
- `run_privileged()` (config writes) and the daemon helpers (`test_daemon`,
  `daemon_version`, `restart_daemon`, `add_user_to_group`) all return the same
  `CommandResult` type (success, returncode, stdout/stderr, error, command), so
  callers handle results uniformly.
>>>>>>> 1b8b488 (English codebase (comments/docstrings) + refactoring)

---

## 4. Flusso utente (7 schede)

| Scheda | Contenuto |
|------|-----------|
| 1 | **Presentazione** (default all'avvio): cos'è GameMode, perché la GUI, come usare `gamemoderun`/Steam/Lutris, disclaimer. Contenuti data-driven da `presentation.json` + i18n |
| 2 | **Generale** (`[general]`): governor, profili, renice, ioprio, ecc. |
| 3 | **GPU** (`[gpu]`): interruttore "Abilita modifica power plan GPU" + power state NVIDIA/AMD (attivi solo con l'interruttore), con banner di avviso |
| 4 | **CPU** (`[cpu]`): pinning dei core (checkbox) e parking dei core (switch) |
| 5 | **Custom** (`[custom]`): card **Notifiche** (due interruttori `toggle_entry` per le notifiche desktop) + script di start/end (liste) + timeout |
| 6 | **Riepilogo**: anteprima del file completo + Salva, Ripristina backup, Ripristina originale |
| 7 | **Daemon**: test/riavvio del daemon `gamemoded` + gestione gruppo `gamemode`, con **console simulata** sempre visibile |

Navigazione con `Adw.ViewStack` + `Adw.ViewSwitcher` nell'header: si passa
liberamente da una scheda all'altra senza ordine forzato (all'avvio si apre la
Presentazione). Ogni scheda di opzioni (Generale, GPU, CPU, Custom) e il
Riepilogo hanno il proprio pulsante **Salva**, che riscrive comunque l'intero
file; la scheda Daemon non salva. Dopo un salvataggio viene mostrato un dialogo
che ricorda di **riavviare il daemon** (scheda Daemon) perché le modifiche
abbiano effetto. Stato delle scelte mantenuto in memoria (solo valori).

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
- **Portabilità Debian/RPM**: i binari (`gamemoded`, `systemctl`, `usermod`,
  `pkexec`, `sudo`, `pkill`) sono risolti con percorsi assoluti
  (`shutil.which` + fallback noti), così funzionano anche con PATH minimo
  (es. sotto `pkexec`) o layout diversi (`/usr/sbin` vs `/sbin`, merged-usr). La
  versione si legge da **`gamemoded --version`** (NON `gamemoderun --version`,
  che è uno script che esegue il comando passato e non gestisce `--version`). Il
  riavvio usa l'unità systemd **utente** (`systemctl --user restart gamemoded`,
  come installata da GameMode) con fallback all'unità di sistema e poi a
  `pkill`. I governor CPU si leggono da **tutti** i file
  `.../cpu*/cpufreq/scaling_available_governors` (non solo cpu0).

Tutti i comandi usano liste di argomenti (`subprocess`), mai `shell=True`.

### 5.1 Packaging e release automatiche

- **`packaging/build.sh`** genera `.deb` e `.rpm` in `dist/`; `VERSION`/`RELEASE`
  sono sovrascrivibili da ambiente (in CI la versione arriva dal tag git).
- **Reset temporaneo**: i post-install (deb `postinst`, rpm `%post`) azzerano
  `/etc/gamemode.ini` (+ `.orig`/`.bak`/`.tmp`/`.session.json`) e le preferenze
  utente `~/.config/gamemode-gui/settings.json` a ogni install/upgrade.
- **CI**: `.github/workflows/build-packages.yml` costruisce i pacchetti e, su
  push di un tag `vX.Y.Z`, li pubblica nella sezione **Releases** di GitHub
  (artefatti allegati alla release; versione presa dal tag). `workflow_dispatch`
  costruisce e carica gli artifact senza creare la release.

---

## 6. Testing

<<<<<<< HEAD
- **`test_core.py`** (senza display): renderer/roundtrip, liste ripetute,
  commit locale atomico + `.orig`/`.bak`/rollback, i18n XML, sessione JSON,
  `privileged.py` in locale.
- **`smoke_test.py`** (con DISPLAY): crea la finestra reale, verifica le schede,
  modifica un valore, salva su un percorso temporaneo (`GAMEMODE_CONFIG`),
  verifica `.orig` e `.session.json` creati e che il file sia completo.
- L'app va lanciata con `python3 main.py`; per i test su percorso scrivibile:
  `GAMEMODE_CONFIG=/tmp/prova/gamemode.ini python3 main.py`.
=======
Chronological summary (oldest first) of how the current state was reached:

| Commit | Date | What it introduced |
|--------|------|--------------------|
| `1ba9267` | 2026-09-30 | Initial GameMode GUI implementation per spec |
| `b3ccb06` | 2026-09-30 | Refactor: single `/etc` file, privileged helper, XML i18n, session state, few files |
| `767bc94` | 2026-09-30 | Fix: always-editable inputs (active dropdowns), natural-size switches, `present()` without args |
| `b90edba` | 2026-10-01 | Reusable widgets: `ChoicePicker` radio buttons (no dropdown), `StepperBox` -/+; `ioprio` as int |
| `8ed0c7d` | 2026-10-01 | Added `agents.md` (work summary and architectural choices) |
| `ebe54f0` | 2026-10-03 | Data-driven tabbed GUI (`options.json`), installed base + `/etc` override, CPU/Custom, deb/rpm packaging |
| `159d563` | 2026-10-09 | Saved language + English file, Filter tab removed, Custom notification toggles, accent styling, refactoring (`fileops.py`, `coerce_value`, `OPTIONS_BY_SECTION`, `SwitchBox`, `style.css`), improved descriptions |
| `4e24e29` | 2026-10-09 | Data-driven Presentation tab (default at startup) + daemon-restart notice on save; `\n` → newline fix |
| `8e460b2` | 2026-10-09 | Packaging: reset on install, GitHub Actions CI/CD release, Debian/RPM command portability |
| `08c4b44` | 2026-10-09 | Docs: single English `README.md` (with the Presentation content) + `agents.md` as the system state |
| (this commit) | 2026-10-09 | English codebase (comments/docstrings) + refactoring: type-rules dispatch table, uniform `CommandResult`, unified restore flows, minor cleanups |

Net effect: the app went from a first spec implementation to a data-driven,
fully localised (it/en), tabbed GUI with a safe atomic write path, a shared
file-I/O module, reusable widgets, an install-time reset, CI/CD releases,
distro-portable system commands, an English codebase and a single type-rules
dispatch table.
>>>>>>> 1b8b488 (English codebase (comments/docstrings) + refactoring)

---

## 7. Indagine: configurazione per singolo gioco? (informativa)

Richiesta informativa documentata e conclusa (nessuna implementazione):

- **Non esiste** una config "per singolo eseguibile" in GameMode: la config è
  unica e globale, con **merging** tra più file in ordine di priorità
  (`$PWD` → `$XDG_CONFIG_HOME` → `/etc` → `/usr/share/gamemode`).
- Il "local data `$PWD`" è risolto alla **directory di lavoro del daemon**
  (`get_current_dir_name()` in `gamemode-config.c`), non per gioco.
- GameMode supporta un filtro "per programma" con `[filter] whitelist/blacklist`
  (nomi di eseguibile): solo accettazione/rifiuto dell'attivazione, non valori
  diversi per gioco. Questa GUI **non** lo gestisce (scheda Filtro rimossa):
  eventuali voci `[filter]` non vengono lette né riscritte.
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
- [x] Tabella dichiarativa completa (`[general]`, `[gpu]`, `[cpu]`, `[custom]`)
- [x] Unico file in `/etc` con helper privilegiato (pkexec/sudo)
- [x] Scrittura atomica + backup + rollback + `.orig`
- [x] i18n via XML (italiano e inglese, elenco lingue dalla config)
- [x] Stato di sessione persistito su JSON
- [x] Widget riutilizzabili (radio picker, stepper, list editor)
- [x] Interfaccia a schede con salvataggio per scheda, test utility, gruppo utente
- [x] Test logica + smoke test interfaccia

Possibili prossimi passi (non concordati):
- [ ] Selettore di lingua nel menu Aiuto
- [ ] Profili predefiniti esportabili/importabili
- [ ] Integrazione di una sezione per-gioco via `gamemoderun`/wrapper
- [ ] Copertura `.po`/`.pot` per gettext (attualmente XML custom)