# Sections

The app is a set of independent **sections**, one folder each (a Python package;
the `__init__.py` files are empty). The general window shows one page per section.

## Shared files (package root)

- `core.py` — `SectionState` (a section's values, one attribute per option) and
  `SectionCore`, the base every **stateful** core extends. It builds the state,
  installs a speaking `get_<key>`/`set_<key>` per option with change notification
  (`subscribe_change_listener`), and provides `reset_to_defaults()` and
  `apply_saved_values()`. A subclass sets `section_id` + `options` and implements
  `render_ini_section()`, `apply_parsed_section()` and `is_option_active()`;
  `allowed_values_for()` is only overridden when the allowed values come from the
  kernel.
- `initializer.py` — the shared loading logic. `extract_section()` parses one
  `[section]` slice out of INI text; `load_section()` resets the core, applies the
  installed base and the `/etc` override (custom appends its lists) and falls back
  to the saved session only when neither text had the section.

## Sections

| Folder | INI block | Files |
| --- | --- | --- |
| `general/` | `[general]` | options + core + ui + initializer |
| `gpu/` | `[gpu]` | options + core + ui + initializer |
| `cpu/` | `[cpu]` | options + core + ui + initializer |
| `custom/` | `[custom]` | options + core + ui + initializer |
| `presentation/` | — (view only) | core + ui + `presentation.json` |
| `daemon/` | — (utilities) | core + ui |

- **Stateful** sections split their code into `options.py` (the option
  descriptors), `core.py` (the section-specific render/read rules), `ui.py` (the
  page) and `initializer.py` (the loading entry point).
- **Stateless** sections only have `core.py` + `ui.py`.

Each folder has its own `agents.md` with the details.
