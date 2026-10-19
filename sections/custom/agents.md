# Section: custom (`[custom]`)

Manages the `[custom]` keys: the scripts run when GameMode starts/ends, the two
notification switches and the script timeout. The options live in `CUSTOM_OPTIONS`
in `options.py`.

## Files

- `options.py` — `CUSTOM_OPTIONS`, the option descriptors (the `[custom]` keys).
- `core.py` — `CustomCore` (extends `SectionCore`). Handles the
  `toggle_entry` coupling (`_effective_list_value`) and the list merge on read
  (`apply_parsed_section(..., append=True)`).
- `ui.py` — `CustomPage`: the **notifications card** at the top (the two
  `toggle_entry` switches) plus the list editors and the timeout stepper.
- `initializer.py` — reads the `[custom]` keys; the start/end lists are **appended**
  (base, then override), as GameMode does. It delegates to `sections/initializer.py`.

## Notes

- A `toggle_entry` switch adds/removes a fixed string to/from a target list
  (`custom.start` / `custom.end`). On read the string is turned into its switch and
  removed from the list; at render time it is re-added, so each entry has a single
  source of truth.
- A `list` option is written as **repeated keys** (one line per item).
