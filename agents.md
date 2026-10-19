# GameMode GUI — architecture

A GTK4 + Libadwaita (Python 3) desktop app to manage the `gamemode.ini`
configuration of the **Feral GameMode** daemon. All code, comments and docs are in
English; only the translation data (`data/locale/*.po`) and the
desktop entry's localised fields are in other languages.

## Internal libraries

The application lives directly in the `gamemode-gui/` folder as a set of small,
testable libraries:

| Package | Responsibility |
| --- | --- |
| `i18n` | gettext catalogs, language detection and `settings.json` |
| `state` | Redux actions/reducers/store and selectors |
| `configuration.py` | paths, INI slices, session, atomic copy-on-write |
| `services` | commands, pkexec/sudo, daemon actions, root helper |
| `sections` | the self-contained `gamemode.ini` sections |
| `ui` | window, pages and the reusable widget library |
| `vendor` | vendored `redux-py` + `Rx` (MIT) |

The top-level modules (`core.py`, `initializer.py`, `configuration.py`, `spec.py`,
`main.py`) are the entry points; new code imports the libraries above directly.

## State flow

Each stateful section declares `section_id` and `options` and extends
`sections.core.SectionCore`. The core is a facade over the shared
`AppStore`:

- speaking `get_<key>()` / `set_<key>()` accessors stay available;
- setters dispatch `SET_OPTION`; the store notifies subscribers;
- `render_ini_section()` and `apply_parsed_section()` remain section-specific.

The store holds `{sections: {id: values}, dirty: bool}`. Reducers are pure;
`Configuration` owns reading and writing the file. `initializer.build_app()`
creates one store, builds every section and calls `Configuration.load()`; `save()`
asks `Configuration.save()` to render all sections and commit atomically.

## i18n

`i18n.tr(key)` reads the gettext catalog for the active language.
Catalogs are `data/locale/<code>.po` compiled to
`data/locale/<code>/LC_MESSAGES/gamemode-gui.mo`; `languages.json` holds the human
language names. The effective language is saved choice > system locale
(`LC_ALL` > `LC_MESSAGES` > `LANG`) > English. The selector lives in the window.
Use `scripts/locales.py compile|check` after editing a `.po` file.

## UI

`ui.pages.SectionPage` builds the common page (header, optional
banner/card, rows, refresh and dependency gating). Section views are tiny
configurations of it. Controls live in `ui.widgets` and are selected
by an option-type registry (`factory.py`), so adding a new type is one builder.

## Layout

```text
gamemode-gui/
├── main.py                    entry point (`python3 main.py`)
├── pyproject.toml             package metadata + console script
├── core.py                    AppCore (orchestration)
├── initializer.py             build/reload the application
├── spec.py                    OptionSpec
├── configuration.py           read/write gamemode.ini atomically
├── services/                  commands, privileged, daemon, helper
├── i18n/                      gettext + settings
├── state/                     Redux store
├── sections/                  one folder per section
├── ui/                        window + pages/ + widgets/
├── vendor/                    vendored Redux/Rx
├── data/                      style.css, locale/*.po, *.mo, languages.json
├── scripts/locales.py         compile/check catalogs
└── test/                      headless tests + smoke test
```

## Conventions

- Comments and docstrings in **English**.
- Prefer speaking names; keep helpers concise.
- Every visible string goes through `tr("key")`.
- GTK is used only in `ui` and the section `ui.py` files; cores and
  services stay headless and testable without a display.
- Reducers stay pure; side effects belong to services or `AppCore`.

## Testing

```bash
python3 test/sections/run_all.py   # one integration test per section
python3 test/test_engine.py        # options + INI (de)serialisation
python3 test/test_app.py           # bootstrap / save / restore / reload
python3 test/test_state.py         # actions, reducers, store, dirty flag
python3 test/smoke_test.py         # real window (needs DISPLAY)
```

## Packaging

`packaging/build.sh` builds the `.deb` and `.rpm` into `dist/` (pure Python/GTK).
It installs `main.py`, the top-level modules and the internal libraries, including
the compiled `.mo` catalogs and the vendored Redux libraries. CI
(`.github/workflows/build-packages.yml`) runs the headless tests before building.

## Caveats

- The install scripts wipe `/etc/gamemode.ini`, its service files and the user
  preferences on every install/upgrade — temporary, for clean testing.
- The `[filter]` section is not managed: because the file is rewritten in full,
  existing `[filter]` entries are dropped on the next save.
- `[gpu]` power-state options only take effect when the file is in `/etc` and
  `apply_gpu_optimisations=accept-responsibility` is set.
