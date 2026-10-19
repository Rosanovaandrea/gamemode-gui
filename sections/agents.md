# Sections

The app is a set of independent **sections**, one folder each under
`sections/` (a Python package). The general window shows one page per section.

## Shared files (package root)

- `core.py` — `SectionState` (attribute view over the store) and `SectionCore`,
  the base every **stateful** core extends. It registers the section defaults in
  the shared Redux store, installs a speaking `get_<key>`/`set_<key>` per option
  and forwards store changes to `subscribe_change_listener`. A subclass sets
  `section_id` + `options` and implements `render_ini_section()`,
  `apply_parsed_section()` and `is_option_active()`; `allowed_values_for()` is
  only overridden when the allowed values come from the kernel.
- `initializer.py` — the shared loading logic. `extract_section()` (from
  `config.ini`) parses one `[section]` slice; `load_section()` resets
  the core, applies the installed base and the `/etc` override (custom appends its
  lists) and falls back to the saved session only when neither text had the
  section.
- `serialization.py` — generic INI rendering/parsing (`render_section`,
  `parse_into`, per-type codecs) used by the general/GPU/CPU cores. The custom
  section keeps its toggle/list rules.

## Sections

| Folder | INI block | Files |
| --- | --- | --- |
| `general/` | `[general]` | options + core + ui + initializer |
| `gpu/` | `[gpu]` | options + core + ui + initializer |
| `cpu/` | `[cpu]` | options + core + ui + initializer |
| `custom/` | `[custom]` | options + core + ui + initializer |
| `presentation/` | — (view only) | core + ui + `presentation.json` |
| `daemon/` | — (utilities) | core (service re-exports) + ui |

- **Stateful** sections split their code into `options.py` (option descriptors),
  `core.py` (state/render/read rules), `ui.py` (the page, usually a small
  `SectionPage` configuration) and `initializer.py` (loading entry point).
- **Stateless** sections only have `core.py` + `ui.py`.

Each folder has its own `agents.md` with the details.
