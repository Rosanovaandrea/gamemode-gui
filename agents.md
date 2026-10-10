# GameMode GUI — architecture

A GTK4 + Libadwaita (Python 3) desktop app to manage the `gamemode.ini`
configuration of the **Feral GameMode** daemon. All code, comments and docs are in
English; only the translation data (`data/locale/*.xml`) and the desktop entry's
localised fields are in other languages.

`README.md` is the user-facing document; this file describes the architecture, and
each `sections/<name>/agents.md` describes one section.

## Approach: self-contained sections (MVC-like)

The app is a set of independent **sections**, one folder each under `sections/`.
A section owns its behavior end to end:

- `core.py` — the section's options, its **state**, the logic to render itself to
  and read itself from `gamemode.ini`, and a **speaking getter/setter per option**
  (`set_reaper_freq`, ...). The core is the only writer of its state.
- `ui.py` — the section page: it builds the widgets and calls the core.
- `initializer.py` — loads the section's values from the config (and the kernel
  where relevant) into the state. Present only for stateful sections.

Sections are deliberately **self-contained**: each defines its own options and its
own INI (de)serialisation, even at the cost of some duplication. Stateless sections
(`presentation`, `daemon`) have only `core.py` + `ui.py`.

The **general** modules only orchestrate:

- `core.py` — joins the sections' own output and performs the shared, app-wide
  operations: atomic **save**, **restore previous**, **factory reset** and the
  **language** choice. No option logic.
- `ui.py` — the window: header (help + language), the section pages, and an
  always-visible **action bar** (save / restore previous / factory reset).
- `initializer.py` — builds the section cores and runs their initializers.

### Flow

- **Save**: the general core asks each section to render its own text, joins them
  and writes the file atomically (temp file + `fsync` + `os.replace`, via `fileops`).
  Writing to `/etc` is delegated to the root helper (`privileged.py`, pkexec/sudo)
  with a `.bak` rollback.
- **Restore previous / factory reset**: restore `.bak` / `.orig`; on success the
  general initializer **reloads every section** (resetting it first), so the UI
  reflects the file exactly.
- **Language**: `i18n.tr(key)` reads `data/locale/<lang>.xml`; the language list
  comes from `~/.config/gamemode-gui/settings.json` and the effective language is
  saved choice > system locale > English. The selector lives in the general window.

## Layout

```
gamemode-gui/
├── main.py            entry point (runs ui.run)
├── core.py            general core (orchestration + save/restore/factory/language)
├── ui.py              general window (gathers the pages + action bar)
├── initializer.py     general initializer (builds and wires the sections)
├── spec.py            OptionSpec: the option descriptor (shared)
├── i18n.py            translations + language preference (shared)
├── fileops.py         atomic write / backup / rollback (shared)
├── privileged.py      root helper for /etc (shared)
├── widgets.py         reusable widgets (shared)
├── data/              style.css, locale/
├── sections/          one folder per section
│   ├── general/  gpu/  cpu/  custom/   (core.py + ui.py + initializer.py)
│   ├── presentation/                   (core.py + ui.py + presentation.json)
│   └── daemon/                         (core.py + ui.py)
└── test/              test_engine.py, test_app.py, smoke_test.py
```

Only these pieces are shared: `spec.py`, `widgets.py`, `i18n.py`, `fileops.py` and
`privileged.py`. Everything else lives with its section.

## Conventions

- Comments and docstrings in **English** and exhaustive: every function says what it
  does, with inline comments for the non-obvious steps.
- **No trivial one/two-line helper functions**: inline them with an explanatory
  comment instead. Prefer **speaking names** over abbreviations.
- Every visible string goes through `tr("key")`; no hardcoded UI text.
- GTK is used only in the `*.py` view files; the section cores and the general core
  stay headless (no GTK import), so they are testable without a display.

## Testing

- `test/test_engine.py` — each section's options and INI (de)serialisation, i18n and
  the root helper (no display).
- `test/test_app.py` — bootstrap, atomic save, `.orig`/`.bak`, restore and reload
  (no display).
- `test/smoke_test.py` — builds the real window (needs a display).

Run the app with `python3 main.py`; on a writable path use
`GAMEMODE_CONFIG=/tmp/try/gamemode.ini python3 main.py`.

## Packaging

`packaging/build.sh` builds the `.deb` and `.rpm` into `dist/` (no compilation: pure
Python/GTK). CI: `.github/workflows/build-packages.yml` builds them and, on a `vX.Y.Z`
tag, publishes them in the GitHub Releases.

## Caveats

- The install scripts (deb `postinst`, rpm `%post`) wipe `/etc/gamemode.ini` (and its
  service files) and the user preferences on every install/upgrade — temporary, for
  clean testing.
- The `[filter]` section is not managed: because the file is rewritten in full, any
  existing `[filter]` entries are dropped on the next save.
- `[gpu]` power-state options only take effect when the file is in `/etc` and
  `apply_gpu_optimisations=accept-responsibility` is set.
