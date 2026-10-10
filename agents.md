# agents.md — GameMode GUI: current state of the system

Technical description of the **current state** of the GameMode GUI project:
what it is made of, how it works today, and how it got here (based on the git
history). It is the internal/developer counterpart of `README.md`, which is the
user-facing document (introduction, install, run, packaging).

---

## 1. Overview

- **Project**: a desktop GUI (GTK4 + Libadwaita, Python 3) to manage the
  `gamemode.ini` configuration file of the **Feral GameMode** daemon.
- **Repository layout**: the application lives in `gamemode-gui/` (the git
  repository). The upstream GameMode C source was used only as a reference
  (config locations, the `[gpu]` "protected" rules, the daemon CLI) and is no
  longer part of the working tree.
- **Goal**: manage **all** `gamemode.ini` options from a GUI, with a **safe write
  strategy** (atomic commit, backup, rollback, restore), a **declarative/tabular**
  INI generation (no `configparser`, so comments are preserved), a **tabbed** user
  flow, and daemon utilities (test, restart, `gamemode` group).
- **Codebase language**: source code, comments, docstrings, `README.md` and this
  file are in **English**. Only the translation data (`locale/*.xml`) and the
  desktop entry's localised fields (`Comment[it]`) are in other languages.

---

## 2. Current architecture

### 2.1 Layout (MVC-like, one folder per section)

```
gamemode-gui/
├── main.py                  entry point (runs ui.run)
├── core.py                  general core: orchestration + save / restore / factory reset / language
├── ui.py                    general window: header + gathers every section page
├── initializer.py           general initializer: builds and wires the sections
├── spec.py                  OptionSpec: the option descriptor (shared with the widget kit)
├── i18n.py                  translations + language preference
├── fileops.py               atomic write / backup / rollback (shared)
├── privileged.py            root helper for /etc (invoked via pkexec/sudo)
├── widgets.py               reusable widgets (build_widget + components)
├── data/                    style.css, locale/
├── sections/                one folder per section
│   ├── general/  gpu/  cpu/  custom/   (core.py + ui.py + initializer.py)
│   ├── presentation/                   (core.py + ui.py + presentation.json)
│   └── daemon/                         (core.py + ui.py, stateless)
└── test/                    tests
    ├── test_engine.py       engine tests (no display)
    ├── test_app.py          application tests (bootstrap / save / restore, no display)
    └── smoke_test.py        interface tests (need DISPLAY, temporary folder)
```

Every **stateful section is self-contained**: its `core.py` defines the section's
options, its own **state** and the logic to render itself to, and read itself from,
gamemode.ini; its `ui.py` builds its own page; its `initializer.py` reads the
section out of gamemode.ini into the state. The core exposes a **speaking
getter/setter per option** (`set_reaper_freq`, `get_apply_gpu_optimisations`, ...).
Stateless sections (`presentation`, `daemon`) have just `core.py` + `ui.py`.

The only shared pieces are the option descriptor (`spec.py`), the widget kit
(`widgets.py`), translations (`i18n.py`), the atomic file ops (`fileops.py`) and the
root helper (`privileged.py`) used by the general save. Every section owns its own
commands and data paths (duplication is accepted, for autonomy). The **general
core** only orchestrates: it joins the sections' own output and performs save /
restore / factory reset / language; the **general UI** gathers the pages; the
**general initializer** wires the sections. All code and comments are in English.

### 2.2 Data-driven options — `options.json`

Every `gamemode.ini` option is described **once** as a JSON entry grouped by
category. Main fields:

```
key             INI key name
description_id  i18n key of the description
label_id        (optional) i18n key of the visible name (default: key)
value_type      int | float | bool | string | choice | list | cores | enable | toggle_entry
widget          stepper | switch | radio | list | cores | entry
range           [min, max] for numeric values (null = unbounded)
choices         allowed values for "choice"
default         default value
special         true if the values are read from the system
special_source  source of the special values (e.g. "cpu_governors")
depends_on      id of another option this one depends on
comment         comment emitted in the INI file
target/entry    for "toggle_entry": the switch adds/removes `entry` to/from the `target` list
```

At category level, `toggle_card_id` is the i18n title of the card that collects
the `toggle_entry` options at the top of the tab (e.g. the `notify-send`
notifications in `[custom]`).

`core.load_categories()` builds the `Category`/`OptionSpec` dataclasses; from them
derive `OPTIONS`, `OPTIONS_BY_ID`, `OPTIONS_BY_SECTION`, `SECTIONS_ORDER` and the
**dynamic** creation of the tabs in `ui.py`. Consequences:

- **adding an option = adding a JSON entry** (no Python code);
- deterministic output: comments and order are preserved exactly;
- rendering is a **pure function**, testable without GUI/display;
- **UI and widgets have no per-option code**: `widgets.build_widget` maps
  `value_type`/`widget` to a standard GTK control.

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

### 2.10 Type rules — single dispatch table

The type-specific logic — how a value is rendered to INI, whether it is written,
how it is parsed from INI and how it is coerced from the JSON session — is
centralised in a single dispatch table `TYPE_RULES` (`core.py`), keyed by
`value_type`. Each entry is a `TypeRules` object with four callables: `render`,
`is_written`, `parse_ini`, `coerce_json`. `render_option()`, `is_written()`,
`values_from_parsed()` and `coerce_value()` all dispatch through `_rules(spec)`,
so adding or changing a value type is a one-place change.

---

## 3. Commands and system integration

All commands use argument lists (`subprocess`), never `shell=True`.

- **Daemon test**: `gamemoded -t`; **version**: `gamemoded --version` (the button
  "Run daemon tests" runs both and shows the raw output in the console).
- **Daemon restart**: `systemctl --user restart gamemoded` (GameMode installs
  `gamemoded.service` as a systemd **user** unit), with fallback to the system unit
  and then to `pkill -TERM gamemoded` on non-systemd systems.
- **`gamemode` group**: check membership; the "Add to group" button runs
  `usermod -aG gamemode $USER` via pkexec (fallback sudo); a logout/login reminder
  is shown **only on success**.

**Portability (Debian/RPM)**:

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

---

## 4. Testing

- **`test/test_engine.py`** (no display): each section's options and INI
  (de)serialisation (round-trip, repeated lists, `[gpu]` dependency, CPU
  pinning/parking, notification `toggle_entry`), i18n (normalisation / detection /
  precedence) and `privileged.py` run locally.
- **`test/test_app.py`** (no display): bootstrap of every section, atomic save,
  `.orig`/`.bak`, restore previous, factory reset and reload (which resets the
  sections).
- **`test/smoke_test.py`** (needs DISPLAY): builds the real window, checks the tabs,
  the global action bar, the kernel-derived choices, editing + saving to a
  temporary path (`GAMEMODE_CONFIG`) and the daemon console.
- The app runs with `python3 main.py`; for tests on a writable path:
  `GAMEMODE_CONFIG=/tmp/try/gamemode.ini python3 main.py`.

---

## 5. Packaging and CI/CD

- **`packaging/build.sh`** builds `.deb` and `.rpm` into `dist/`; `VERSION`/`RELEASE`
  are overridable from the environment (in CI the version comes from the git tag),
  and in `build_rpm` the spec `Version`/`Release` are aligned with the tarball.
- **Debian**: `dpkg-deb`; **RPM**: `rpmbuild` (from `rpm-build`/`rpm`). The spec
  disables `__os_install_post` for a reproducible noarch build.
- **Temporary reset on install**: the deb `postinst` and the rpm `%post` wipe
  `/etc/gamemode.ini` (+ `.orig`/`.bak`/`.tmp`/`.session.json`) and the user
  preferences `~/.config/gamemode-gui/settings.json` on every install/upgrade.
- **CI**: `.github/workflows/build-packages.yml` builds both packages and, on a tag
  push `vX.Y.Z`, publishes them in the GitHub **Releases** section (artifacts
  attached to the release; version from the tag). `workflow_dispatch` builds and
  uploads the artifacts without creating a release.

---

## 6. Git history / milestones

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

---

## 7. Current behaviours and caveats

- **Config reset on install (temporary)**: every install/upgrade wipes
  `/etc/gamemode.ini` (+ service files) and the user preferences. This is
  intentional for now (clean testing) and should be revisited before stable
  releases.
- **Filter tab removed**: the GUI does not manage `[filter]` `whitelist`/`blacklist`
  anymore. Because the file is rewritten in full, any existing `[filter]` entries
  are **not read nor rewritten** (they are dropped on the next save).
- **Language is persisted** in `~/.config/gamemode-gui/settings.json` and takes
  precedence over the system locale.
- **`igpu_desiredgov`** is a CPU governor value (GameMode applies it via the same
  `cpugovctl`), so it is read from the same kernel source as the other governors.
- **`[gpu]` power state** only takes effect if the file is in `/etc` (or
  `/usr/share/gamemode`) and only with `apply_gpu_optimisations=accept-responsibility`.

---

## 8. Possible future work

- [ ] Remove the temporary install-time reset before stable releases.
- [ ] Exportable/importable configuration profiles.
- [ ] Per-game integration via `gamemoderun`/wrappers.
- [ ] `.po`/`.pot` gettext coverage (currently a custom XML format).
- [ ] Optionally make the platform-profile list kernel-derived
      (`/sys/firmware/acpi/platform_profile_choices`, not present on all systems).
