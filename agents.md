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
  (lookup array + flag di attivazione), non con `configparser` (che perderebbe
  i commenti).
- Flusso utente a **step** (Generale → Filtro → GPU → Riepilogo → Riavvio).
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

**Perché**: il daemon di GameMode applica la sezione `[gpu]` (power state GPU,
overclock NVIDIA/AMD) **solo** leggendo file "safe" (`/etc`, `/usr/share/gamemode`).
I file in `$PWD` e `$XDG_CONFIG_HOME` sono "unsafe": la sezione `[gpu]` viene
letta e **scartata silenziosamente** (`gamemode-config.c`:
`if (!load_protected) { ... return 1; }`).

Conservare una config in `.config` E una in `/etc` sarebbe stato confuso e
inutile. Abbiamo quindi un **unico file di sistema**, con tutti i privilegi che
comporta.

Conseguenze:
- Tutte le scritture passano per un **helper privilegiato** (pkexec/sudo).
- La GUI chiede la password amministratore solo al momento del salvataggio
  (non all'avvio).

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

### 2.4 Approccio dichiarativo tabellare (single source of truth)

**Decisione**: ogni opzione di `gamemode.ini` è descritta **una volta sola**
in `core.py` come `OptionSpec` (dataclass):

```python
OptionSpec(
    section="general", key="reaper_freq", type="int", default=5,
    min_value=1, template="reaper_freq={value}", description=tr("..."),
    comment="; ...")
```

Il renderer (`render_ini`) attraversa la tabella e, per ogni opzione col flag
di attivazione `True`, emette commento + riga formattata, raggruppando per
sezione. Vantaggi:
- **aggiungere un'opzione = aggiungere una riga** alla tabella;
- l'output è deterministico: commenti e ordine preservati esattamente;
- il rendering è una **funzione pura**, testabile senza GUI/display;
- nessun `configparser` che perda i commenti.

### 2.5 Flag di attivazione in memoria ("Includi") + sessione

**Decisione**: ogni opzione ha un flag booleano in memoria che decide se viene
scritta nel file. All'avvio i flag vengono **ricostruiti leggendo il file
esistente** (chiave presente ⇒ `True`).

Interazione con la GUI:
- l'input è **sempre editabile** (modificare un valore ⇒ flag `True`, come da
  spec §3.2);
- il checkbox "Includi" permette di **escludere esplicitamente** un'opzione dal
  file anche se ne stai modificando il valore;
- quando non inclusa, la riga è solo "attenuata" (opacity), mai disabilitata —
  questo era un bug reale che bloccava i menù a tendina.

Al commit, lo stato delle scelte (flag + valori) viene salvato anche in
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

### 2.7 Pochi file, interfaccia divisa per step

**Decisione** (refactoring richiesto dall'utente): minimizzare i file. Da una
struttura iniziale a molteplici moduli (`core/` + `ui/` da ~15 file) siamo
passati a **6 file di codice**:

```
gamemode-gui/
├── main.py          entry point (delega a ui.main)
├── core.py          logica pura (tabella, renderer, config, i18n, daemon, sessione)
├── ui.py            tutta l'interfaccia GTK, divisa per step con commenti
├── widgets.py       widget riutilizzabili (vedi 2.8)
├── privileged.py    helper root per /etc
├── locale/it.xml    traduzioni
├── test_core.py     test della logica (senza display)
└── smoke_test.py    test dell'interfaccia (richiede DISPLAY, usa cartella temp)
```

`ui.py` è organizzata in "capitoli" numerati (1..10), uno per step, così è
facile navigare il file.

### 2.8 Widget riutilizzabili in `widgets.py`

**Decisione**: raccogliere i componenti riutilizzabili in un modulo dedicato,
per non duplicare la costruzione dei widget tra gli step:

- **`ChoicePicker`** — **niente dropdown**: un gruppo di **radio button** in un
  FlowBox. Selezionare una voce disattiva le altre. È la scelta che ha risolto
  il problema dei menù a tendina (vedi 3.3).
- **`StepperBox`** — pulsanti **− / +** con etichetta centrale, vincolati a
  `min`/`max`, con supporto a step decimali (per i float).
- **`ListEditor`** — lista di stringhe per `whitelist`/`blacklist`.
- **`OptionRow`** — riga dichiarativa completa: checkbox "Includi" + widget
  costruito in base al `type` della spec.

Tutti espongono la stessa interfaccia valori: `get_value()`, `set_value()`,
`set_sensitive()`, callback `on_change`.

### 2.9 `ioprio` come valore numerico (0–7)

**Decisione**: `ioprio` è stato trasformato da "choice" con valori speciali
(`off`/`reset`) a **int 0–7**, gestito con `StepperBox` (−/+). Motivazione:
semplicità d'uso e coerenza con le altre opzioni numeriche; i valori speciali
erano fonte di ambiguità nella UI.

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

## 4. Flusso utente (5 step)

| Step | Contenuto |
|------|-----------|
| 1 | **Generale** (`[general]`): governor, profili, renice, ioprio, ecc. |
| 2 | **Filtro** (`[filter]`): whitelist / blacklist |
| 3 | **GPU** (`[gpu]`): power state NVIDIA/AMD con banner di avviso |
| 4 | **Riepilogo**: anteprima del file, Salva, Ripristina backup, Ripristina originale |
| 5 | **Riavvio**: riavvia il daemon `gamemoded` + gestione gruppo `gamemode` |

Navigazione con `Adw.ViewStack` + pulsanti Indietro/Avanti e indicatore di
progresso (1/5 … 5/5). Salvataggio dello stato tra gli step in memoria.

---

## 5. Comandi e utility

- **Test daemon**: `gamemoded -t` e `gamemoderun --version` (pulsante "Test"
  nell'header, output in un dialogo).
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
- **`smoke_test.py`** (con DISPLAY): crea la finestra reale, naviga gli step,
  modifica un valore, salva su un percorso temporaneo (`GAMEMODE_CONFIG`),
  verifica `.orig` e `.session.json` creati.
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
- [x] 5-step flow, test utility, gruppo utente
- [x] Test logica + smoke test interfaccia

Possibili prossimi passi (non concordati):
- [ ] Selettore di lingua nel menu Aiuto
- [ ] Profili predefiniti esportabili/importabili
- [ ] Integrazione di una sezione per-gioco via `gamemoderun`/wrapper
- [ ] Copertura `.po`/`.pot` per gettext (attualmente XML custom)