# GUI di Configurazione per Feral GameMode

Applicazione desktop (GTK4 + Libadwaita) per gestire in modo visuale, sicuro
e intuitivo il file `gamemode.ini` del daemon **Feral GameMode**.

## Filosofia (come concordato)

- **File unico in `/etc/gamemode.ini`** (percorso privilegiato). Niente doppia
  gestione tra `.config` e `/etc`: la GUI lavora solo sul file di sistema, dove
  il daemon applica *anche* le ottimizzazioni `[gpu]`.
- **Commit con riscrittura totale del file** (copy-on-write):
  1. contenuto nuovo su `gamemode.ini.tmp` + `fsync`;
  2. il file attivo precedente è copiato in `gamemode.ini.bak`;
  3. `os.replace(tmp, gamemode.ini)` (atomico);
  4. `gamemode.ini.orig` = copia "vergine" iniziale, creata una sola volta;
  5. su errore: rollback automatico da `.bak`.
- **Solo le opzioni attive finiscono nel file**: un'opzione viene scritta solo
  se il suo valore differisce dal default (o se la lista non è vuota), perché
  GameMode applica già i default da sé. Alcune opzioni (`[gpu]`) richiedono un
  interruttore abilitante (`apply_gpu_optimisations=accept-responsibility`).
- **Stato delle scelte in memoria** (solo valori) e salvataggio in
  `gamemode.ini.session.json` a ogni commit, così lo stato è riapribile.
- **i18n via file esterni XML** (`locale/<lang>.xml`): oggi solo italiano ma
  configurabile. Inserire un altro XML + impostare `GAMEMODE_LANG` attiva la
  nuova lingua. Niente stringhe hardcoded nel codice.
- **Opzioni data-driven** (`options.json`): ogni opzione è una voce JSON per
  categoria con `key`, `description_id`, `value_type`, `range`, `widget`,
  `default`, `special`, ecc. Aggiungere/modificare un'opzione = modificare il
  JSON, non il codice. I valori `special` (es. governor CPU, core CPU per il
  pinning) non sono statici: vengono letti dal sistema.
- **Pochi file** (refactoring): logica in `core.py`, interfaccia in `ui.py`,
  **widget riutilizzabili in `widgets.py`** (`build_widget` standard per tipo,
  scelta a radio button, stepper -/+, editor di liste) così da non duplicare
  codice tra le schede.
- **Navigazione a schede** (`Adw.ViewStack` + `Adw.ViewSwitcher`): Generale,
  Filtro, GPU, Riepilogo, Daemon. Ogni scheda di opzioni ha il proprio pulsante
  **Salva**, che riscrive il file con tutte le opzioni attive. La scheda GPU ha
  un interruttore **"Abilita modifica power plan GPU"** che scrive
  `apply_gpu_optimisations=accept-responsibility`: le altre voci `[gpu]` sono
  utilizzabili e scritte solo quando è attivo.

## Struttura

```
gamemode-gui/
├── main.py           entry point (avvia ui.main)
├── options.json      TUTTE le opzioni per categoria (single source of truth,
│                     data-driven: una voce JSON per opzione)
├── core.py           logica: caricamento definizioni, valori speciali dal
│                     sistema, renderer, config manager, i18n, sessione
├── ui.py             TUTTA l'interfaccia GTK, schede generate dai dati
├── widgets.py        widget riutilizzabili: build_widget (per tipo),
│                     ChoicePicker (radio, niente dropdown), StepperBox (-/+),
│                     ListEditor, OptionRow (nome+descrizione su una riga)
├── privileged.py     helper eseguito come root (pkexec/sudo) per scrivere /etc
├── locale/it.xml     traduzioni (italiano, configurabile)
├── test_core.py      test della logica (senza GUI)
└── smoke_test.py     test dell'interfaccia (richiede DISPLAY, usa cartella
                      temporanea, non tocca la config reale)
```

## Dipendenze

- Python 3.10+
- PyGObject (GTK4, libadwaita)

```bash
# Fedora
sudo dnf install python3-gobject gtk4 libadwaita
# Debian/Ubuntu
sudo apt install python3-gi gir1.2-gtk-4.0 gir1.2-adw-1
```

## Esecuzione

```bash
cd gamemode-gui
python3 main.py
```

La prima scrittura in `/etc/gamemode.ini` richiede la password amministratore
(via `pkexec`, con fallback `sudo`).

Per provare senza toccare `/etc` (percorso scrivibile temporaneo):

```bash
GAMEMODE_CONFIG=/tmp/prova/gamemode.ini python3 main.py
```

## Test

```bash
python3 test_core.py    # logica, senza display
python3 smoke_test.py   # interfaccia (serve DISPLAY), usa cartella temporanea
```

## Pacchetti (`.deb` / `.rpm`)

Lo script `packaging/build.sh` genera entrambi i pacchetti in `dist/`:

```bash
packaging/build.sh
```

- **`.deb`** (Debian/Ubuntu): `Depends: python3, python3-gi, gir1.2-gtk-4.0,
  gir1.2-adw-1, gamemode` (più `pkexec | policykit-1`; `Recommends: sudo`).
- **`.rpm`** (Fedora/RHEL): `Requires: python3, python3-gobject, gtk4,
  libadwaita, gamemode, polkit` (più `Recommends: sudo`).

Entrambi installano:

```
/usr/bin/gamemode-gui                                        # launcher
/usr/share/gamemode-gui/{main,core,ui,widgets,privileged}.py
/usr/share/gamemode-gui/{options.json,locale/it.xml}
/usr/share/applications/io.github.gamemodegui.GameModeGui.desktop
/usr/share/icons/hicolor/scalable/apps/io.github.gamemodegui.GameModeGui.svg
```

Dopo l'installazione l'app compare nel menu (icona standard "GameMode GUI") e si
avvia da lì o con il comando `gamemode-gui`. Per l'RPM serve `rpmbuild`
(pacchetto `rpm-build`); in mancanza si può indicare un binario con
`RPMBUILD=/path/rpmbuild packaging/build.sh`.

## Quale file configura la GUI (e quali legge il daemon)

GameMode carica **più file** e li fonde in ordine (`gamemode-config.c`), con
`CONFIG_NAME = gamemode.ini` e 4 posizioni:

| Ordine | Percorso | Tipo | Note |
|---|---|---|---|
| 1 | `/usr/share/gamemode/gamemode.ini` | protected | config "spedita" dal pacchetto (il suo `example/gamemode.ini`) |
| 2 | `/etc/gamemode.ini` | protected | config dell'amministratore |
| 3 | `~/.config/gamemode.ini` (o `$XDG_CONFIG_HOME`) | unsafe | config utente |
| 4 | `$PWD/gamemode.ini` | unsafe | directory di lavoro del daemon |

Le **liste** (`whitelist`/`blacklist`, `start`/`end`) si accodano; i **valori
scalari sovrascrivono** quelli dei file precedenti → vince l'ultimo letto.

**La GUI usa il file installato come base e scrive gli override in
`/etc/gamemode.ini`.** Il percorso del file installato è rilevato a runtime
(`$XDG_DATA_DIRS` poi `/usr/local/share` e `/usr/share` →
`<datadir>/gamemode/gamemode.ini`; per i test si può forzare con `GAMEMODE_BASE`).
I valori mostrati sono quelli **effettivi**, cioè il risultato del merge
base + `/etc` (liste accodate, scalari sovrascritti), esattamente come li vede il
daemon. I commenti delle voci scritte in `/etc` vengono presi dal file installato
quando disponibili.

`/etc/gamemode.ini` è la scelta corretta perché:
- è nel percorso pensato per la configurazione dell'amministratore;
- viene letto **dopo** il file spedito dal pacchetto, quindi ne sovrascrive i
  valori senza doverlo modificare (il file in `/usr/share` appartiene al
  pacchetto e viene sostituito dagli aggiornamenti);
- è una delle **due sole posizioni "protected"** in cui il daemon accetta la
  sezione `[gpu]` (l'altra è `/usr/share/gamemode`).

Al primo salvataggio, se `/etc/gamemode.ini` non esiste, il file `.orig`
ripristinabile viene seedato con il contenuto del file installato, così
"Ripristina originale" torna ai default forniti dal pacchetto.

**Cambia da distro a distro?**
- `/etc/gamemode.ini` è **fisso** su tutti i sistemi (path hardcoded nel sorgente).
- Il file "spedito" dipende dal *prefix* di build: normalmente
  `/usr/share/gamemode/gamemode.ini`, ma con prefix diverso (es. `/usr/local`)
  diventa `/usr/local/share/gamemode/gamemode.ini`. Inoltre non tutti i
  pacchetti installano l'esempio (`with-examples`): su alcune distro quel file
  può non esistere e resta solo `/etc`.
- Attenzione: un eventuale `~/.config/gamemode.ini` o `$PWD/gamemode.ini`
  (**unsafe**) può sovrascrivere i valori scritti in `/etc` per le sezioni non
  `[gpu]`.

La scheda **Riepilogo** mostra sempre entrambi i percorsi: l'override gestito
(`Override gestito (scritto dalla GUI): /etc/gamemode.ini`) e la base installata
(`Base installata (sola lettura): /usr/share/gamemode/gamemode.ini`).

## Note su `[gpu]` e "power state"

Le voci `nv_powermizer_mode` (NVIDIA: 0=Adaptive, 1=Prefer Max, 2=Auto) e
`amd_performance_level` (AMD: auto/low/high) sono le uniche opzioni che gestiscono
i *power state* della GPU, e il daemon **le applica solo leggendo i percorsi
"protected"** (`/usr/share/gamemode` e `/etc`; la sezione `[gpu]` è ignorata
altrove, con log esplicito). Gestendo il file in `/etc`, la GUI le rende
realmente effettive: all'ingresso in GameMode il daemon applica il power state
scelto e al termine lo ripristina.